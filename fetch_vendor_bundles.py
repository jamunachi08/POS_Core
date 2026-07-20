#!/usr/bin/env python3
"""
fetch_vendor_bundles.py — one-time helper to download Vue / Pinia / vue-i18n
bundles into alphax_pos_suite/public/dist/vendor/

Run this once on your laptop (any computer with internet):

    python3 fetch_vendor_bundles.py

Then commit the resulting files in public/dist/vendor/ to git.
After they're committed, the cashier will load them from your bench's
own /assets/... URL — no runtime CDN fetch, no first-open delay, works
on offline benches.

Re-run this only if you want to upgrade Vue/Pinia/vue-i18n versions.
Edit the VERSIONS dict below before re-running.
"""
import os
import sys
import urllib.request

VERSIONS = {
    "vue.global.prod.js": (
        # Vue 3 — the SFC compiler-included build
        "https://unpkg.com/vue@3.5.13/dist/vue.global.prod.js"
    ),
    "pinia.iife.prod.js": (
        # Pinia 3.x — self-contained, no vue-demi dependency
        "https://unpkg.com/pinia@3.0.3/dist/pinia.iife.prod.js"
    ),
    "vue-i18n.global.prod.js": (
        # Vue I18n 9.x — Vue 3 compatible
        "https://unpkg.com/vue-i18n@9.14.0/dist/vue-i18n.global.prod.js"
    ),
}

def main():
    target = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "alphax_pos_suite",
        "alphax_pos_suite",
        "public",
        "dist",
        "vendor",
    )
    os.makedirs(target, exist_ok=True)
    print(f"Downloading vendor bundles to {target}\n")

    ok = 0
    for filename, url in VERSIONS.items():
        out = os.path.join(target, filename)
        print(f"  {filename:30s} <- {url}")
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "alphax-pos-core/15.5.x fetcher"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(out, "wb") as f:
                f.write(data)
            size_kb = len(data) / 1024
            print(f"  {'':30s}    saved ({size_kb:.1f} KB)")
            ok += 1
        except Exception as e:
            print(f"  {'':30s}    ERROR: {e}", file=sys.stderr)

    print(f"\nDone — {ok}/{len(VERSIONS)} files downloaded.")
    if ok == len(VERSIONS):
        print("\nNext step:")
        print("  git add alphax_pos_suite/alphax_pos_suite/public/dist/vendor/")
        print("  git commit -m 'Embed Vue/Pinia/vue-i18n vendor bundles'")
        print("  git push")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
