# AlphaX POS Suite v15.10.4 — cashier boot fix (`export async function`)

Drop-in replacement for the whole repo. Every check below passed on this
exact tree before packaging.

## The failure

    ESM load error in api/bridgeInstall.js:
      SyntaxError: Unexpected token 'export'
    Failed to load api/bridgeInstall.js
    AlphaX cashier failed to boot

The cashier SPA is not built by Vite at runtime. `main.js` fetches each
`sfc/**/*.js` file as text, rewrites its module syntax, and evaluates it
through `new Function()`. The export rewriter in `loadESMAsObject()`
handled exactly four shapes:

    export const X = ...
    export let X = ...
    export function X ...
    export default ...

`api/bridgeInstall.js` — added in the zero-touch onboarding work — exports
four **async** functions:

    export async function probeBridge(...)
    export async function applyToken(...)
    export async function waitForBridge(...)
    export async function copyToClipboard(...)

`export async function` matched none of the four rules, so the literal
word `export` survived into the `new Function()` body and V8 rejected it.
`bridgeInstall` is loaded in Phase A of the boot chain, and Phase A
rethrows, so the whole cashier died before Vue was ever created.

A second, silent defect sat behind it: the loader re-attached exported
declarations to `__exports` by scanning for `^function\s+NAME`. Even if
the `export` keyword had been stripped naively, `async function probeBridge`
would not have matched that scan, so `window.AlphaXApi.bridgeInstall`
would have come back empty and every consumer would have thrown
`probeBridge is not a function` instead.

## The fix

`alphax_pos_suite/public/dist/vendor/cashier/main.js` — `loadESMAsObject()`
export rewriter replaced. It now handles every export form ES2022 allows
in this codebase, and records each exported name as it goes rather than
inferring names from a second scan:

| Form | Handling |
|---|---|
| `export const\|let\|var X = ...` | assigned inline — `const X = __exports.X = ...` — so TDZ and evaluation order are unchanged |
| `export function X` / `export function* X` | keyword stripped, binding re-attached in the tail |
| `export async function X` / `export async function* X` | **new** — same treatment |
| `export class X` | **new** — keyword stripped, re-attached in the tail |
| `export default ...` | `__exports.default = ...` |
| `export { a, b as c }` | **new** — expanded to `__exports.a = a; __exports.c = b;`, multi-line lists included |

Three further hardening changes in the same function:

1. **Line-anchored patterns.** All rules now match `^[ \t]*export` instead
   of `export` anywhere. The word `export` inside a comment, a string, or
   a template literal is no longer rewritten.
2. **Readable failure.** Any `export` or `import` still standing after the
   rewrite throws with the offending line quoted:
   `unsupported module syntax -> export { x } from './y'`.
   Previously this class of bug surfaced only as `Unexpected token`, with
   no line and no file context beyond the truncated dump.
3. **Non-fatal tail.** Re-attachment is `try { __exports.X = X } catch {}`,
   and the legacy scan for unexported top-level declarations is preserved,
   so no module that relied on the old accidental exposure regresses.
   Truncation of the debug dump raised from 2 000 to 4 000 chars.

No change to `api/bridgeInstall.js` itself — the file was valid ESM. The
loader was the defect.

## Verification on this tree

| Check | Result |
|---|---|
| `python verify_tree.py` | tree verified — safe to push |
| `python build_spa_payload.py` | 70 files packed, payload hash back in sync |
| `node simulate.js` (jsdom full boot) | BOOT OK, geometry, rail, cart, pay dialog, tender — all pass |
| Loader sweep, all 20 `sfc/**/*.js` modules | every module evaluates; every named import across all `.js` and `.vue` files resolves against the namespace that will hold it |

`api/bridgeInstall.js` now resolves to:

    probeBridge, applyToken, launchInstaller, waitForBridge, copyToClipboard

## Deploy

    git add -A
    git commit -m "v15.10.4: loader handles export async function / class / export lists"
    git push

Then on the site:

    bench --site tkakenda.frappe.cloud migrate
    bench --site tkakenda.frappe.cloud clear-cache

`__version__` is `15.10.4`. The cashier page stamps `?v=<installed
version>` on every SPA asset URL, so the bump is what evicts the cached
`main.js?v=15.10.3` the browser is currently executing. If the old file
persists behind the edge cache, one hard reload on `/app/alphax-cashier`
clears it.

`spa_payload.py` was rebuilt in this release because `main.js` changed —
the embedded copy is what restores SPA files when the asset pipeline is
broken, and `verify_tree.py` fails the push if it drifts.
