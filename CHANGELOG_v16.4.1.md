# AlphaX POS Suite — v16.4.1

Packaging guard only; no functional change.

## Why

A Docker image build (`bench get-app file:///…/apps/alphax_pos_suite`) failed with:

    uv pip install -e …/alphax_pos_suite
    × Failed to resolve dependencies for `frappe` (v15.124.0)
    ╰─▶ Package `pypika` was included as a URL dependency …
    hint: `frappe` was included because `alphax-pos-suite` (v15.10.4) depends on `frappe>=15.0.0`

The build context held **v15.10.4**, whose packaging listed `frappe>=15.0.0`
as a pip dependency. uv then tries to install Frappe itself from PyPI, and
Frappe's own `pypika` git pin is a URL dependency that uv refuses to take
transitively. Frappe and ERPNext must be declared only under
`[tool.bench.frappe-dependencies]`, which bench resolves against the apps
already in the bench.

Current releases (v16.x) declare no pip dependencies; the same
`uv pip install -e` command installs v16.4.1 cleanly (`Requires:` empty).

## Change

`scripts/health_check.py` now fails if `frappe` or `erpnext` appears in
`setup.py` `install_requires` or `pyproject.toml` `[project].dependencies`.

## Fixing the build

Point the build context at this release instead of the old checkout:

    cd <docker context>/apps/alphax_pos_suite
    git fetch origin && git checkout main && git pull   # or replace the folder with this zip
    git log -1 --oneline                                # confirm it is 16.4.1
    grep __version__ alphax_pos_suite/__init__.py

Then rebuild the image (add `--no-cache` for the app stage if Docker reuses
the old layer).
