# AlphaX POS Suite v15.6.8 — Restore Lost Assets + Push Safety

## What happened

The v15.6.7 push silently DELETED the entire
`alphax_pos_suite/public/dist/vendor/` tree — 57 files, including the
whole cashier SPA. Root cause: Git for Windows fails to check out
paths longer than 260 characters unless `core.longpaths` is enabled;
the deep SPA paths errored out of `git reset --hard`, and the
subsequent `git add -A` staged their absence as deletions. The
register's diagnostics card reported it precisely: "root 1: exists,
NO SPA … serving from: NOWHERE".

## Changes

- Full asset tree present again (this zip is, as always, the complete
  correct state).
- Error card's "Open POS Hub" now points to `/app/alphax-pos-hub` —
  workspaces route by NAME slug, and `/app/alphax-pos` 404s (second
  screenshot).
- New `verify_tree.py` at the repo root: pre-push gate that checks
  core.longpaths, sentinel files, minimum tree sizes, python parse,
  and conflict markers. **Run `python verify_tree.py` before every
  push from now on.** It would have caught both of the last two
  incidents before they reached the server.

## Push procedure (Windows-safe)

    git config core.longpaths true      # THE fix — once per machine
    git fetch origin
    git reset --hard origin/main
    # extract this zip to a SHORT path first (e.g. C:\px), then copy in:
    #   PowerShell, from the repo root:
    #   Expand-Archive "$env:USERPROFILE\Downloads\POS_Core-v15.6.8-restore.zip" C:\px -Force
    #   robocopy C:\px . /E /NFL /NDL /NJH /NJS
    #   Remove-Item C:\px -Recurse -Force
    python verify_tree.py               # must say "safe to push"
    git add -A
    git commit -m "v15.6.8 - restore vendor assets, push safety gate"
    git push origin main
