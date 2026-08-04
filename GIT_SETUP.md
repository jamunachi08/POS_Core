# Git setup & pushing to GitHub

This folder is already an initialised Git repository (it has a `.git`
folder), with a sensible `.gitignore` and an initial commit. You can push
it straight to GitHub.

## First time — push to a new/empty GitHub repo

1. Create an empty repository on GitHub (no README, no .gitignore — keep it
   empty so there's nothing to merge).
2. In a terminal (Git Bash on Windows is fine), from inside this folder:

   ```bash
   git remote add origin https://github.com/jamunachi08/alphax_pos_suite.git
   git branch -M main
   git push -u origin main
   ```

   Replace the URL with your actual repository URL.

## If the repo already has commits (e.g. you pushed before)

Pull/rebase first, then push:

```bash
git remote add origin https://github.com/jamunachi08/alphax_pos_suite.git
git fetch origin
git rebase origin/main      # or: git merge origin/main
git push -u origin main
```

## Everyday workflow

```bash
git add -A
git commit -m "Describe what changed"
git push
```

## Installing on a bench from Git

Once it's on GitHub:

```bash
bench get-app https://github.com/jamunachi08/alphax_pos_suite.git
bench --site <your-site> install-app alphax_pos_suite
```

## Notes

- The cashier's runtime files under
  `alphax_pos_suite/alphax_pos_suite/public/dist/` are committed on purpose
  (this app has no build step). Don't delete them.
- `__pycache__`, `*.pyc`, `node_modules`, and editor/OS junk are ignored.
- Line endings are normalised to LF via `.gitattributes`, which avoids the
  "whole file changed" noise when moving between Windows and Frappe Cloud.
- License note: `license.txt`/`hooks.py` currently say **MIT** while the
  README says **Proprietary**. Decide which you want and make them match
  before publishing the repo.
