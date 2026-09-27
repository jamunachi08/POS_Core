/**
 * SFC loader test harness.
 *
 * Runs in Node to exercise the SFC loader's parser, import rewriter,
 * and <script setup> transformer against every real .vue file in the
 * project. We can't run Vue.compile in Node (no DOM), but we CAN
 * verify:
 *
 *   1. Every .vue file splits into template/script/style cleanly
 *   2. Every <script setup>'s imports rewrite without throwing
 *   3. Every transformed setup body parses as valid JS
 *
 * Run: node sfc-loader.test.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Stub the browser globals the loader expects.
global.window = {
  Vue: { compile: () => () => null, defineComponent: (x) => x },
  Pinia: {},
  VueI18n: {},
};
global.document = { createElement: () => ({ setAttribute: () => {}, appendChild: () => {} }), head: { appendChild: () => {} } };
global.fetch = () => Promise.reject(new Error('no fetch in test harness'));

// Load the loader.
const loaderSrc = fs.readFileSync(
  path.join(__dirname, '..', '..', 'alphax_pos_suite', 'public', 'dist', 'cashier', 'sfc-loader.js'), 'utf8');
new vm.Script(loaderSrc).runInThisContext();

const SFC_ROOT = path.join(__dirname, '..', '..', 'alphax_pos_suite', 'public', 'dist', 'cashier', 'sfc');

const results = { ok: 0, fail: 0, errors: [] };

function walkVue(dir) {
  const out = [];
  for (const f of fs.readdirSync(dir)) {
    const full = path.join(dir, f);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) out.push(...walkVue(full));
    else if (f.endsWith('.vue')) out.push(full);
  }
  return out;
}

function testOne(filePath) {
  const rel = path.relative(SFC_ROOT, filePath).replace(/\\/g, '/');
  const source = fs.readFileSync(filePath, 'utf8');
  try {
    const sfc = window.AlphaXSFC.splitSFC(source, rel);

    // Each .vue must have either a template or a script.
    if (!sfc.template && !sfc.scriptBlock) {
      throw new Error('no <template> or <script> block found');
    }

    if (sfc.scriptBlock) {
      const rewritten = window.AlphaXSFC.rewriteImports(
        sfc.scriptBlock.content, rel);

      // Imports should all be gone or replaced.
      if (/^\s*import\s+/m.test(rewritten)) {
        const stray = rewritten.match(/^\s*import\s+.*$/m)[0];
        throw new Error(`stray import after rewrite: ${stray}`);
      }

      // If <script setup>, run the transformer.
      if (sfc.scriptBlock.isSetup) {
        const t = window.AlphaXSFC.transformScriptSetup(rewritten, rel);
        // Parse the wrapped function body as JS.
        const wrapped = `
          (function(__alphax_props, __alphax_ctx) {
            let __props_decl, __emits_decl, __expose_decl;
            const __ctx_props = __alphax_props;
            const __ctx_emit = __alphax_ctx && __alphax_ctx.emit;
            const __ctx_expose = __alphax_ctx && __alphax_ctx.expose;
            ${t.body}
            return ${t.returnObj};
          })
        `;
        try {
          new vm.Script(wrapped, { filename: rel });
        } catch (e) {
          throw new Error(`setup body did not parse as JS: ${e.message}`);
        }
      }
    }

    results.ok++;
  } catch (e) {
    results.fail++;
    results.errors.push({ file: rel, error: e.message });
  }
}

const files = walkVue(SFC_ROOT);
console.log(`Testing ${files.length} .vue files...\n`);

for (const f of files) testOne(f);

if (results.errors.length) {
  console.log('FAILURES:');
  for (const e of results.errors) {
    console.log(`  ${e.file}: ${e.error}`);
  }
  console.log();
}

console.log(`Result: ${results.ok}/${files.length} passed, ${results.fail} failed.`);
process.exit(results.fail ? 1 : 0);
