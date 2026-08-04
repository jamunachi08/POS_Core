# DEPLOY v15.5.7 — step by step for Noor

## What this version fixes

The cashier page on neo15 was loading but couldn't find its display
files (Vue/Pinia/vue-i18n bundles). This version permanently embeds
those files in the codebase so the cashier loads even when the bench
can't reach the internet.

---

## Step 1 — Run the fetch script (5 seconds, 1 command)

The repo includes `fetch_vendor_bundles.py` in its root. This script
downloads the 3 vendor files we need.

Open a terminal **in your local clone of the alphax-pos-core repo** and run:

```bash
python3 fetch_vendor_bundles.py
```

You should see output like:

```
Downloading vendor bundles to /Users/you/.../public/dist/vendor

  vue.global.prod.js              <- https://unpkg.com/vue@3.5.13/...
                                       saved (467.2 KB)
  pinia.iife.prod.js              <- https://unpkg.com/pinia@3.0.3/...
                                       saved (12.3 KB)
  vue-i18n.global.prod.js         <- https://unpkg.com/vue-i18n@9.14.0/...
                                       saved (45.7 KB)

Done — 3/3 files downloaded.

Next step:
  git add alphax_pos_suite/alphax_pos_suite/public/dist/vendor/
  git commit -m 'Embed Vue/Pinia/vue-i18n vendor bundles'
  git push
```

If you get an error about `python3 not found`, install Python from
python.org first (or run `python` instead of `python3`).

---

## Step 2 — Commit the files via git bash

In the same terminal (or your usual git bash window):

```bash
git add alphax_pos_suite/alphax_pos_suite/public/dist/vendor/
git commit -m "v15.5.7: Embed vendor bundles for offline cashier load"
git push
```

You should see git upload 3 files (about 525 KB total).

---

## Step 3 — Deploy on Frappe Cloud

1. Open https://frappecloud.com/dashboard
2. Click **Benches** → click your bench
3. You should see "Updates available" banner at the top
4. Click **Show Updates** → make sure `alphax_pos_suite` is checked → click **Deploy**
5. Wait for the deploy to finish (~5-10 minutes). Watch the **Deploys** tab.
6. Status should go: Pending → Running → Success

---

## Step 4 — Verify the cashier loads

1. Open https://neo15.k.frappe.cloud/app/alphax-pos-v2
2. **Hard-refresh the page** (Ctrl+Shift+R on Windows/Linux, Cmd+Shift+R on Mac)
3. The cashier should boot and show its UI.

If you still see the error card:

1. Press F12 to open browser dev tools
2. Click the **Network** tab
3. Click "Retry / إعادة المحاولة"
4. Look for `vue.global.prod.js` in the network list — what's the status?
   - **200 (green)** — vendor file loaded but something else broke. Send me the full console output.
   - **404 (red)** — the files didn't deploy. Most likely the git push or the Frappe Cloud deploy didn't include them. Re-run step 2 carefully.

---

## What if git status shows nothing changed?

That can happen if `.gitignore` is blocking the vendor folder. Run:

```bash
cat .gitignore | grep -i "vendor\|dist\|public"
```

If you see lines like `**/vendor/` or `**/dist/`, that's the problem.
Edit `.gitignore` and remove those lines. Then re-run:

```bash
git add -A alphax_pos_suite/alphax_pos_suite/public/dist/vendor/
git status   # should now show 3 new files
git commit -m "v15.5.7: vendor bundles"
git push
```

---

## What if the Python script fails to download?

The script needs internet on whatever machine you run it on. If you
get a network error, you can also download the 3 files manually:

1. https://unpkg.com/vue@3.5.13/dist/vue.global.prod.js
2. https://unpkg.com/pinia@3.0.3/dist/pinia.iife.prod.js
3. https://unpkg.com/vue-i18n@9.14.0/dist/vue-i18n.global.prod.js

Right-click → Save As, save each one into:

`alphax_pos_suite/alphax_pos_suite/public/dist/vendor/`

Then continue with Step 2.

---

## I'm here if anything breaks

Send me what you see (especially network tab screenshots or console
errors) and I can tell you what's wrong in real time.
