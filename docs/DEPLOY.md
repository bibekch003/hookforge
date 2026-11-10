# Deploying Hookforge

Three routes, easiest first. All of them run the **real application** — the FastAPI
backend with ffmpeg and OpenCV — not a static screenshot gallery. That matters: this app
processes video, so it cannot be hosted on GitHub Pages or Netlify.

Nothing here needs a credit card. Every route is undoable by deleting one thing.

---

## Route A — GitHub Codespaces (no signups, ~2 minutes)

Best for: recording the demo video, or using the app yourself right now.

1. Open https://github.com/bibekch003/hookforge
2. Green **Code** button → **Codespaces** tab → **Create codespace on main**
3. Wait for it to build. The devcontainer installs dependencies and builds the sample clip
   automatically.
4. In the terminal:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. A popup offers to open port 8000 in the browser — click **Open in Browser**. (Or go to
   the **Ports** tab and click the globe icon next to 8000.)

The URL looks like `https://<random>-8000.app.github.dev`. To let someone else open it,
right-click the port → **Port Visibility** → **Public**.

**Free tier:** 60 core-hours/month on a personal account. A codespace stops after 30 min
idle.

**Undo:** https://github.com/codespaces → the `...` menu next to the codespace → **Delete**.

---

## Route B — Render (a permanent public URL)

Best for: a link you can put in the submission form.

1. Open https://render.com and sign up **with GitHub** (no card needed).
2. **New +** → **Blueprint**.
3. Pick the `bibekch003/hookforge` repository → **Connect**.
4. Render reads `render.yaml` from the repo. Click **Apply**.
5. Wait ~3–5 minutes for the first build. You get `https://hookforge-xxxx.onrender.com`.

**Free tier:** the service sleeps after ~15 minutes of no traffic, so the first visit after
a nap takes ~30 seconds to wake. Filesystem is ephemeral — uploads and renders disappear on
restart (the bundled sample clip still works, so `/api/demo` is always available).

**Undo:** dashboard → the service → **Settings** → **Delete Service**.

---

## Route C — Hugging Face Spaces (Docker, generous free CPU)

Best for: a public demo with more RAM than Render's free tier.

1. Open https://huggingface.co/new-space, sign up free.
2. Name it `hookforge`, **SDK: Docker**, hardware **CPU basic (free)**, visibility **Public**.
3. Create the Space, then in the **Files** tab → **Add file** → **Upload files**.
4. Upload the contents of this repo. Easiest path: use the terminal inside a Codespace
   (Route A) where the repo is already cloned, add the Space as a git remote and push:

   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/hookforge
   git push space main
   ```

   Hugging Face will ask for a **write token** (Settings → Access Tokens → New token, type
   *write*), used as the password.

The Dockerfile in this repo already listens on port 7860, which is what Spaces expects. The
app appears at `https://huggingface.co/spaces/<your-username>/hookforge` with a running
`*.hf.space` URL.

**Undo:** the Space → **Settings** → **Delete this Space**.

---

## Read this before you make the URL public

The app has **no authentication**. Anyone with the URL can upload a video to your instance
and consume its CPU. For a hackathon demo that is usually fine, but:

- keep `HOOKFORGE_MAX_UPLOAD_MB` low (the blueprint sets 60)
- don't leave an expensive instance running after judging
- if it gets abused, delete the service — nothing is persisted anyway

If you later want it hardened, the honest options are an API key on `POST /api/analyze` plus
a request-size limit at the proxy, or putting the whole thing behind Cloudflare Access.

## What does *not* survive a redeploy

`data/` is ephemeral on every host above: uploads, thumbnails, renders and the SQLite
history. The app rebuilds what it needs per request, and the sample clip lives in the repo,
so a cold instance still demos correctly. Persistent disk is a paid feature on Render and
Fly; Spaces gives you a `/data` volume on paid hardware only.
