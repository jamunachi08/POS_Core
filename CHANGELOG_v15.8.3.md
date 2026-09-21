# AlphaX POS Suite v15.8.3 — Repo hygiene: the .gitignore that ate the SPA

No code changes. The repo's .gitignore contained a bare `dist/`
pattern (intended for Python build artifacts) which matches at ANY
depth — silently excluding alphax_pos_suite/public/dist/, the entire
committed SPA vendor tree, from every `git add` ever run. Root cause
of every "vendor tree missing after push" incident in this app's
history; the v15.7.5 payload self-heal has been compensating on every
deploy. Confirmed on GitHub: public/ showed only js/.

Fixed: `dist/` and `build/` are now root-anchored (`/dist/`,
`/build/`) with a warning comment; verified with git check-ignore that
the vendor tree is now committable while Python build artifacts remain
ignored.

## Repairing the existing GitHub repo

1. Replace .gitignore with this release's copy.
2. Copy this release's alphax_pos_suite/public/dist/ into your local
   repo (same path).
3. git add -A && git commit -m "v15.8.3: commit SPA vendor tree, fix gitignore" && git push
4. Deploy on Frappe Cloud.

If the pre-build validation still fails after the full tree lands,
open the failed step's log — the specific message identifies the
remainder exactly.
