/**
 * Test the ESM-as-object loader by running the same import-rewrite +
 * export-rewrite over every real .js module in stores/, api/,
 * composables/, and locales/.
 *
 * We can't actually execute them (they import vue/pinia and call browser
 * APIs), but we can verify the rewritten source is syntactically valid
 * JavaScript.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

global.window = {
  Vue: {},
  Pinia: {},
  VueI18n: {},
};
global.document = { createElement: () => ({ setAttribute: () => {}, appendChild: () => {} }), head: { appendChild: () => {} } };

const loaderSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'alphax_pos_suite', 'public', 'dist', 'cashier', 'sfc-loader.js'), 'utf8');
new vm.Script(loaderSrc).runInThisContext();

const SFC_ROOT = path.join(__dirname, '..', '..', 'alphax_pos_suite', 'public', 'dist', 'cashier', 'sfc');

const TEST_DIRS = ['stores', 'api', 'composables', 'locales'];
const results = { ok: 0, fail: 0, errors: [] };

function rewriteAsModule(source, path) {
  let body = window.AlphaXSFC.rewriteImports(source, path);
  body = body.replace(/export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                      'const $1 = __exports.$1 =');
  body = body.replace(/export\s+let\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/g,
                      'let $1 = __exports.$1 =');
  body = body.replace(/export\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)/g,
                      'function $1');
  body = body.replace(/export\s+default\s+/g, '__exports.default = ');

  const fnNames = [];
  const fnRe = /^function\s+([A-Za-z_$][A-Za-z0-9_$]*)/gm;
  let mm;
  while ((mm = fnRe.exec(body))) fnNames.push(mm[1]);
  const tail = fnNames.length
    ? '\n' + fnNames.map(n => `__exports.${n} = ${n};`).join('\n')
    : '';

  return `(function() { const __exports = {}; ${body} ${tail} return __exports; })`;
}

for (const dir of TEST_DIRS) {
  const dirPath = path.join(SFC_ROOT, dir);
  if (!fs.existsSync(dirPath)) continue;
  for (const f of fs.readdirSync(dirPath)) {
    if (!f.endsWith('.js')) continue;
    const full = path.join(dirPath, f);
    const rel = path.join(dir, f).replace(/\\/g, '/');
    const source = fs.readFileSync(full, 'utf8');
    try {
      const wrapped = rewriteAsModule(source, rel);
      try { new vm.Script(wrapped, { filename: rel }); }
      catch (e) {
        throw new Error(`rewritten module did not parse: ${e.message}`);
      }
      // Imports should all be gone.
      if (/^\s*import\s+/m.test(wrapped)) {
        throw new Error(`stray import after rewrite`);
      }
      results.ok++;
    } catch (e) {
      results.fail++;
      results.errors.push({ file: rel, error: e.message });
    }
  }
}

if (results.errors.length) {
  console.log('FAILURES:');
  for (const e of results.errors) console.log(`  ${e.file}: ${e.error}`);
  console.log();
}
console.log(`Result: ${results.ok}/${results.ok + results.fail} passed.`);
process.exit(results.fail ? 1 : 0);
