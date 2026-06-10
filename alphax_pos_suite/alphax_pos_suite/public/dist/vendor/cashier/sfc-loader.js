/**
 * AlphaX SFC loader — runtime compilation of .vue files.
 *
 * The cashier UI ships its 25 components as plain .vue Single-File
 * Component files inside the app's public folder. This loader fetches
 * each one, splits the <template>, <script setup>, and <style> sections,
 * transforms <script setup> into a setup() function, and registers the
 * result as a Vue component.
 *
 * Why not Vite?
 *   Vite needs Node + npm at build time. Frappe Cloud doesn't allow
 *   either. Runtime compilation costs ~50ms once on first load and
 *   ~80KB more bundle (Vue's compiler). For a cashier register, that's
 *   a one-time cost we happily pay to avoid the npm install ritual on
 *   every install.
 *
 * Constraints handled:
 *   - <script setup> with imports
 *   - defineProps / defineEmits / defineExpose
 *   - Top-level await (we don't support it, fail loud)
 *   - <style scoped> with hash-based scope IDs
 *   - vue-i18n's useI18n, Pinia's useFooStore, etc — accessed via globals
 *
 * Constraints NOT handled (intentional):
 *   - TypeScript syntax (we'd need a TS transformer; project is plain JS)
 *   - <script setup lang="ts">
 *   - JSX
 *   - .css/.scss imports inside <script> (use <style> instead)
 *
 * If you find a component that doesn't compile, the error log will
 * include the component name, the section that failed, and the line.
 * Do not silently swallow errors.
 */

(function (global) {
  'use strict';

  const Vue = global.Vue;
  const Pinia = global.Pinia;
  const VueI18n = global.VueI18n;

  if (!Vue) throw new Error('AlphaX SFC loader: window.Vue is not loaded yet.');

  // ---------------------------------------------------------------------
  // Section splitter — finds <template>, <script>, <style> blocks
  // ---------------------------------------------------------------------

  function splitSFC(source, filename) {
    const out = { template: '', scriptBlock: null, styles: [], filename };
    let i = 0;

    while (i < source.length) {
      // Skip whitespace and HTML comments at top level
      while (i < source.length && /\s/.test(source[i])) i++;
      if (source.slice(i, i + 4) === '<!--') {
        const end = source.indexOf('-->', i);
        i = end < 0 ? source.length : end + 3;
        continue;
      }
      if (i >= source.length) break;

      // Match an opening tag of one of our blocks
      const tagMatch = source.slice(i).match(/^<(template|script|style)([^>]*)>/);
      if (!tagMatch) {
        // Anything else at top level — skip past it
        i = source.indexOf('<', i + 1);
        if (i < 0) break;
        continue;
      }

      const tag = tagMatch[1];
      const attrs = parseAttrs(tagMatch[2]);
      const openEnd = i + tagMatch[0].length;

      // Find the *matching* close tag, accounting for nested tags of the
      // same name (e.g. <template #footer> inside an outer <template>).
      const closeStart = findMatchingClose(source, openEnd, tag);
      if (closeStart < 0) {
        throw new Error(`SFC ${filename}: unterminated <${tag}> block`);
      }
      const content = source.slice(openEnd, closeStart);
      const blockEnd = closeStart + (`</${tag}>`).length;

      if (tag === 'template') {
        if (out.template) throw new Error(`SFC ${filename}: multiple <template> blocks`);
        out.template = content;
      } else if (tag === 'script') {
        if (out.scriptBlock) throw new Error(`SFC ${filename}: multiple <script> blocks`);
        out.scriptBlock = { content, isSetup: 'setup' in attrs, attrs };
      } else if (tag === 'style') {
        out.styles.push({ content, scoped: 'scoped' in attrs, attrs });
      }

      i = blockEnd;
    }

    return out;
  }

  function parseAttrs(s) {
    const attrs = {};
    const re = /(\w[\w-]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+)))?/g;
    let m;
    while ((m = re.exec(s))) attrs[m[1]] = m[2] ?? m[3] ?? m[4] ?? '';
    return attrs;
  }

  /**
   * Find the close tag </name> at the same nesting depth as the opening tag.
   * Starts scanning from `start`. Counts opens of the same tag name to handle
   * cases like a <template> that contains <template #slotname> children.
   *
   * Self-closing variants (<tag .../>) and HTML void elements don't apply
   * here — these are SFC outer blocks, always a real close tag.
   */
  function findMatchingClose(source, start, tagName) {
    const openRe = new RegExp(`<${tagName}(?:\\s[^>]*)?>`, 'g');
    const closeRe = new RegExp(`</${tagName}\\s*>`, 'g');
    let depth = 1;
    let pos = start;
    while (pos < source.length) {
      openRe.lastIndex = pos;
      closeRe.lastIndex = pos;
      const o = openRe.exec(source);
      const c = closeRe.exec(source);
      if (!c) return -1;
      if (o && o.index < c.index) {
        depth++;
        pos = o.index + o[0].length;
      } else {
        depth--;
        if (depth === 0) return c.index;
        pos = c.index + c[0].length;
      }
    }
    return -1;
  }


  // ---------------------------------------------------------------------
  // Import rewriter — turns ES imports into references to globals.
  //
  //   import { ref, computed } from 'vue'         -> const { ref, computed } = Vue;
  //   import { useI18n } from 'vue-i18n'           -> const { useI18n } = VueI18n;
  //   import { defineStore } from 'pinia'          -> const { defineStore } = Pinia;
  //   import Foo from './Foo.vue'                  -> const Foo = AlphaXSFC.cache['./Foo.vue'];
  //   import { useHardwareStore } from '../stores/hardware' -> const { useHardwareStore } = AlphaXStores;
  //   import { bridge } from '../api/bridge'       -> const { bridge } = AlphaXApi.bridge;
  //   import { i18n } from '../locales'            -> const { i18n } = AlphaXLocales;
  //   import './styles/globals.css'                -> (stripped — CSS is loaded separately)
  //
  // The rewriter is regex-based. SFC scripts are small (rarely > 300
  // lines) and the import shapes we use are limited and consistent —
  // regex is fine. We do NOT try to parse JS in general.
  // ---------------------------------------------------------------------

  const IMPORT_RE = /^\s*import\s+(.+?)\s+from\s+['"](.+?)['"]\s*;?\s*$/gm;
  const SIDE_EFFECT_IMPORT_RE = /^\s*import\s+['"](.+?)['"]\s*;?\s*$/gm;

  function rewriteImports(scriptContent, filename) {
    let out = scriptContent;

    // Strip side-effect-only imports (CSS, etc).
    out = out.replace(SIDE_EFFECT_IMPORT_RE, '');

    // Rewrite named/default imports.
    out = out.replace(IMPORT_RE, function (full, importClause, src) {
      const repl = mapImport(importClause.trim(), src.trim(), filename);
      return repl;
    });

    return out;
  }

  function mapImport(clause, src, filename) {
    // Determine the global expression to replace `from src` with.
    let globalExpr;

    if (src === 'vue') {
      globalExpr = 'Vue';
    } else if (src === 'vue-i18n') {
      globalExpr = 'VueI18n';
    } else if (src === 'pinia') {
      globalExpr = 'Pinia';
    } else if (src.endsWith('.vue')) {
      globalExpr = `(window.AlphaXSFC.cache[${JSON.stringify(resolvePath(src, filename))}] || (function(){ throw new Error("Component not loaded: " + ${JSON.stringify(src)}); })())`;
    } else if (src.match(/\/stores\//)) {
      globalExpr = 'window.AlphaXStores';
    } else if (src.match(/\/composables\//)) {
      globalExpr = 'window.AlphaXComposables';
    } else if (src.match(/\/api\//)) {
      const apiName = src.split('/').pop().replace(/\.js$/, '');
      globalExpr = `window.AlphaXApi.${apiName}`;
    } else if (src.match(/\/locales/)) {
      globalExpr = 'window.AlphaXLocales';
    } else if (src.startsWith('./') || src.startsWith('../')) {
      // Same-folder relative import (e.g. "./mock" from api/client.js).
      // Derive the namespace from the importing file's location.
      // filename is something like "api/client.js" -> namespace AlphaXApi
      // Then for "./mock" we want AlphaXApi.mock if we treat it as another module
      // in the same namespace. For locales/index.js -> "./en" we want
      // AlphaXLocales (and 'en'/'ar' get pre-loaded directly into AlphaXLocales
      // by the bootstrap).
      const fromDir = filename.split('/').slice(0, -1).join('/');
      const ns = namespaceForDir(fromDir);
      if (!ns) {
        throw new Error(
          `SFC ${filename}: unrecognized import source ${JSON.stringify(src)} ` +
          `(can't determine namespace for ./* import in ${fromDir}/)`
        );
      }
      // For the locales/ case where en.js/ar.js export defaults we expose
      // them directly on the namespace as `en` / `ar`.
      const importedName = src.split('/').pop().replace(/\.js$/, '');
      globalExpr = `(window.${ns}.${importedName} || window.${ns})`;
    } else {
      throw new Error(`SFC ${filename}: unrecognized import source ${JSON.stringify(src)}`);
    }

    // Now translate the import clause. Same as before.
    if (clause.startsWith('{')) {
      const names = clause.replace(/[{}]/g, '').trim();
      const translated = names.split(',').map(s => {
        const parts = s.trim().split(/\s+as\s+/);
        return parts.length === 2 ? `${parts[0]}: ${parts[1]}` : parts[0];
      }).filter(Boolean).join(', ');
      return `const { ${translated} } = ${globalExpr};`;
    }

    if (clause.includes(',')) {
      const [def, named] = clause.split(',', 2);
      const namedClean = named.trim().replace(/[{}]/g, '');
      const translated = namedClean.split(',').map(s => {
        const parts = s.trim().split(/\s+as\s+/);
        return parts.length === 2 ? `${parts[0]}: ${parts[1]}` : parts[0];
      }).filter(Boolean).join(', ');
      return `const ${def.trim()} = (${globalExpr}.default || ${globalExpr}); const { ${translated} } = ${globalExpr};`;
    }

    return `const ${clause.trim()} = (${globalExpr}.default || ${globalExpr});`;
  }

  function namespaceForDir(dir) {
    // Map a folder-style path to its global namespace.
    if (dir === 'stores' || dir.endsWith('/stores')) return 'AlphaXStores';
    if (dir === 'api' || dir.endsWith('/api')) return 'AlphaXApi';
    if (dir === 'composables' || dir.endsWith('/composables')) return 'AlphaXComposables';
    if (dir === 'locales' || dir.endsWith('/locales')) return 'AlphaXLocales';
    if (dir === 'components' || dir.endsWith('/components')) return null; // .vue handled elsewhere
    return null;
  }

  function resolvePath(relPath, fromFile) {
    // Resolve "./Foo.vue" or "../components/Bar.vue" against fromFile.
    const fromDir = fromFile.split('/').slice(0, -1);
    const parts = relPath.split('/');
    const out = fromDir.slice();
    for (const p of parts) {
      if (p === '' || p === '.') continue;
      if (p === '..') out.pop();
      else out.push(p);
    }
    return out.join('/');
  }


  // ---------------------------------------------------------------------
  // <script setup> -> setup() transformer
  //
  // Strategy: wrap the (already-rewritten) setup body in a function. That
  // function returns an object containing every top-level binding so the
  // template can reference them. defineProps/defineEmits/defineExpose
  // are intercepted via shadow definitions inside the wrapper.
  // ---------------------------------------------------------------------

  function transformScriptSetup(rewrittenScript, filename) {
    // Find every top-level binding so we can return them at the end of setup().
    // We look for `const X`, `let X`, `var X`, `function X`, `async function X`.
    // We also handle destructuring: `const { a, b } = ...`, `const [c, d] = ...`.
    const bindings = new Set();

    // Lines we can safely skip
    const isSkippable = (line) =>
      /^\s*$/.test(line) ||
      /^\s*\/\//.test(line) ||
      /^\s*\/\*/.test(line);

    const lines = rewrittenScript.split('\n');
    let depth = 0;
    for (const line of lines) {
      if (isSkippable(line)) continue;

      // Track brace depth so we only collect TOP-LEVEL declarations.
      const beforeDepth = depth;
      depth += countChar(line, '{') - countChar(line, '}');
      if (beforeDepth !== 0) continue;

      // const/let/var X = ... or const X
      let m = line.match(/^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*[=;]/);
      if (m) { bindings.add(m[1]); continue; }

      // const { a, b: c, d = 1 } = ...
      m = line.match(/^\s*(?:const|let|var)\s+\{([^}]+)\}\s*=/);
      if (m) {
        const inner = m[1];
        const re = /([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::\s*([A-Za-z_$][A-Za-z0-9_$]*))?/g;
        let mm;
        while ((mm = re.exec(inner))) {
          bindings.add(mm[2] || mm[1]);
        }
        continue;
      }

      // const [a, b] = ...
      m = line.match(/^\s*(?:const|let|var)\s+\[([^\]]+)\]\s*=/);
      if (m) {
        m[1].split(',').forEach(s => {
          const name = s.trim().split('=')[0].trim();
          if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) bindings.add(name);
        });
        continue;
      }

      // function X / async function X
      m = line.match(/^\s*(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)/);
      if (m) { bindings.add(m[1]); continue; }
    }

    // Intercept defineProps/defineEmits/defineExpose.
    // We rewrite them to capture into __props_decl, __emits_decl, __expose_decl.
    // Then the wrapper uses those to assemble the component options.
    let body = rewrittenScript;
    body = body.replace(/\bdefineProps\s*\(/g, '(__props_decl = ');
    body = body.replace(/\bdefineEmits\s*\(/g, '(__emits_decl = ');
    body = body.replace(/\bdefineExpose\s*\(/g, '(__expose_decl = ');
    // The above leaves trailing ")" intact. Each becomes:
    //   const x = (__props_decl = [...])  — a comma operator-ish assignment
    // which works because the RHS is the assignment expression's value.

    // Build the return object — only include bindings the template can use.
    const bindingList = Array.from(bindings).filter(name =>
      !['__props_decl','__emits_decl','__expose_decl'].includes(name)
    );

    const returnObj = bindingList.length
      ? `{ ${bindingList.join(', ')} }`
      : '{}';

    return {
      bindings: bindingList,
      hasProps: /defineProps/.test(rewrittenScript),
      hasEmits: /defineEmits/.test(rewrittenScript),
      hasExpose: /defineExpose/.test(rewrittenScript),
      body,
      returnObj,
    };
  }

  function countChar(s, ch) {
    let n = 0;
    // Naive — doesn't handle braces inside strings/regexes/comments.
    // Acceptable because our SFC scripts use one-line declarations
    // for top-level state, and string literals rarely contain braces.
    for (let i = 0; i < s.length; i++) if (s[i] === ch) n++;
    return n;
  }


  // ---------------------------------------------------------------------
  // Style injection
  // ---------------------------------------------------------------------

  let styleSeq = 0;
  function injectStyles(styles, scopeId, filename) {
    for (const style of styles) {
      const css = style.scoped ? scopeCss(style.content, scopeId) : style.content;
      const tag = document.createElement('style');
      tag.setAttribute('data-alphax-sfc', filename);
      tag.textContent = css;
      document.head.appendChild(tag);
    }
  }

  function scopeCss(css, scopeId) {
    // Naive scoping — append [data-v-XXXX] to every selector.
    // Skips @keyframes, @media wrappers (their inner selectors are scoped).
    const attr = `[${scopeId}]`;
    return css.replace(/(^|\})([^{}@]+)\{/g, function (m, prev, selector) {
      const scoped = selector.split(',').map(s => {
        s = s.trim();
        if (!s) return s;
        // Don't scope :root, html, body
        if (/^(:root|html|body)\b/.test(s)) return s;
        return s + attr;
      }).join(', ');
      return prev + scoped + ' {';
    });
  }


  // ---------------------------------------------------------------------
  // Component factory
  // ---------------------------------------------------------------------

  function buildComponent(sfc, name) {
    const scriptRewritten = sfc.scriptBlock
      ? rewriteImports(sfc.scriptBlock.content, sfc.filename)
      : '';

    const isSetup = sfc.scriptBlock && sfc.scriptBlock.isSetup;
    const transform = isSetup
      ? transformScriptSetup(scriptRewritten, sfc.filename)
      : null;

    // Compile template. Vue.compile returns a render function.
    const compiled = Vue.compile(sfc.template, {
      isCustomElement: (tag) => tag.startsWith('alphax-'),
    });

    // Scope ID for scoped styles
    const scopeId = `data-v-${hashString(sfc.filename).toString(36).slice(0, 8)}`;
    if (sfc.styles.length) injectStyles(sfc.styles, scopeId, sfc.filename);

    let setupFn;
    if (isSetup) {
      // Build a function that runs the setup body and returns bindings.
      // Wrap in IIFE to give a fresh scope per instance.
      // Note: we use `__alphax_props` and `__alphax_emit` so the user's
      // own `const props = defineProps(...)` doesn't collide with our names.
      const fnBody = `
        let __props_decl, __emits_decl, __expose_decl;
        const __ctx_props = __alphax_props;
        const __ctx_emit = __alphax_ctx.emit;
        const __ctx_expose = __alphax_ctx.expose;
        ${transform.body}
        if (typeof __expose_decl !== 'undefined') __ctx_expose(__expose_decl);
        return ${transform.returnObj};
      `;
      try {
        setupFn = new Function('__alphax_props', '__alphax_ctx', fnBody);
      } catch (e) {
        console.error(`SFC compile error in ${sfc.filename}:\n${fnBody}`);
        throw new Error(`SFC ${sfc.filename}: setup function build failed: ${e.message}`);
      }
    }

    const componentDef = {
      name: name,
      render: compiled,
      __scopeId: sfc.styles.some(s => s.scoped) ? scopeId : undefined,
    };

    if (setupFn) {
      // We need props and emits declared OUTSIDE setup, but the
      // <script setup> author wrote them as defineProps()/defineEmits()
      // inside it. Run the setup body once with dummy ctx to harvest
      // those declarations, then build the real component options.
      const harvest = harvestPropsEmits(transform.body, sfc.filename);
      if (harvest.props !== null) componentDef.props = harvest.props;
      if (harvest.emits !== null) componentDef.emits = harvest.emits;
      componentDef.setup = setupFn;
    } else if (sfc.scriptBlock) {
      // <script> (not setup) — execute as a module that exports default.
      const wrapped = `
        const __exports = {};
        ${scriptRewritten.replace(/export\s+default\s+/, '__exports.default = ')}
        return __exports.default;
      `;
      try {
        const factory = new Function(wrapped);
        Object.assign(componentDef, factory());
      } catch (e) {
        throw new Error(`SFC ${sfc.filename}: <script> evaluation failed: ${e.message}`);
      }
    }

    return Vue.defineComponent(componentDef);
  }

  function harvestPropsEmits(body, filename) {
    // Static-only extraction of defineProps([...]) / defineProps({...}) /
    // defineEmits([...]). We don't try to evaluate; we capture the
    // literal argument as JS source and eval it in isolation.
    const result = { props: null, emits: null };

    const propsM = body.match(/__props_decl\s*=\s*([\s\S]+?)\)/);
    if (propsM) {
      try { result.props = (new Function(`return ${propsM[1]};`))(); }
      catch (e) {
        throw new Error(`SFC ${filename}: defineProps() argument is not a static literal`);
      }
    }
    const emitsM = body.match(/__emits_decl\s*=\s*([\s\S]+?)\)/);
    if (emitsM) {
      try { result.emits = (new Function(`return ${emitsM[1]};`))(); }
      catch (e) {
        throw new Error(`SFC ${filename}: defineEmits() argument is not a static literal`);
      }
    }
    return result;
  }

  function hashString(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }


  // ---------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------

  const cache = {};       // path -> compiled component
  const sourceCache = {}; // path -> raw .vue source
  const inFlight = {};    // path -> fetch promise

  async function fetchSource(path) {
    if (sourceCache[path]) return sourceCache[path];
    if (inFlight[path]) return inFlight[path];
    const url = `/assets/alphax_pos_suite/dist/vendor/cashier/sfc/${path}`;
    const p = fetch(url).then(async (r) => {
      if (!r.ok) throw new Error(`Could not fetch SFC ${url}: HTTP ${r.status}`);
      const text = await r.text();
      sourceCache[path] = text;
      return text;
    });
    inFlight[path] = p;
    try { return await p; } finally { delete inFlight[path]; }
  }

  /**
   * Load and compile a single .vue file by relative path.
   *   await AlphaXSFC.load('App.vue')
   *   await AlphaXSFC.load('components/CartPanel.vue')
   */
  async function load(path) {
    if (cache[path]) return cache[path];
    const source = await fetchSource(path);
    const sfc = splitSFC(source, path);
    const name = path.split('/').pop().replace(/\.vue$/, '');
    const component = buildComponent(sfc, name);
    cache[path] = component;
    return component;
  }

  /**
   * Bulk-load a list of components (so child component refs are
   * resolved by the time their parents try to use them).
   */
  async function loadAll(paths) {
    return Promise.all(paths.map(load));
  }

  global.AlphaXSFC = {
    load, loadAll, cache, sourceCache,
    splitSFC, rewriteImports, transformScriptSetup,  // exposed for testing
  };

})(window);
