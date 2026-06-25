# Autoclipping — Source of Truth

Single source of truth for this project. **`PROJECT_STATUS.md`** is the running,
plain-English status log; this file is the durable technical reference. `README.md`
exists only to carry the Hugging Face Space config frontmatter (do not delete it).

**Maintainer:** devproxa (evedarkness18@gmail.com) · **Last updated:** 2026-06-26

---

## 1. What this is

A Docker-based automation pipeline running on a Hugging Face **Space**, orchestrated
by **Hermes Agent** (NousResearch). The pipeline: fetch a video transcript → pick
clip-worthy moments → cut vertical clips → analyze each clip → publish to socials.

A FastAPI app (`app.py`) serves a health check and a `POST /tools/{name}` bridge
that exposes each pipeline tool for direct testing.

## 2. Hosting & git (read first)

| Property | Value |
|----------|-------|
| Host | Hugging Face Spaces |
| Repo / remote | `https://huggingface.co/spaces/devproxa/Autoclipping` (this is `origin`) |
| Visibility | Private |
| Space SDK | `docker` (set in `README.md` frontmatter) |
| App port | `7860` |
| Deploy | **push to `main`** → Space rebuilds & redeploys automatically |
| Persistent storage | bucket `devproxa/Autoclipping-storage` mounted at **`/data`** (runtime only) |

- **The git remote IS the Space — it is the source of truth. Do NOT push to GitHub.**
  The GitHub account tied to the Space belongs to the **client**. Use the HF `origin`
  only; do not add a GitHub remote.
- Auth: HTTPS with a **fine-grained HF write token** as the git password (username
  `devproxa`). Stored in Git Credential Manager, not in the repo. Re-auth once per
  new machine.

## 3. Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app: `GET /` health check (probes `hermes` on PATH) + `POST /tools/{tool_name}` bridge. |
| `config.py` | Loads env vars (`.env` locally / Space secrets in prod). Exposes `ANTHROPIC_API_KEY`, `FAL_KEY`, `BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. |
| `entrypoint.sh` | Container entrypoint: installs/restores Hermes into `/data` (background) then execs uvicorn. |
| `Dockerfile` | Image build — see §5. |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `httpx`, `python-dotenv`, `fal-client`, `requests`. |
| `tools/` | Pipeline tool modules — see §4. |
| `tools_manifest.json` | Tool contract (input/output schemas) for the bridge / a future MCP wrapper. |
| `README.md` | **HF Space config frontmatter** (`sdk: docker`, `app_port: 7860`) + short blurb. Mandatory for the Space to build. |
| `PROJECT_STATUS.md` | Plain-English status + build-notes log. |
| `.env` | Secrets, gitignored — never committed. |

## 4. Pipeline tools (`tools/`)

Plain functions, no framework coupling. Callable directly, via `POST /tools/{name}`,
or (eventually) via an MCP wrapper.

| Tool | Function | Notes |
|------|----------|-------|
| Transcript | `transcript.get_transcript(video_url)` | YouTube → `youtube-transcript-api` (~1s pacing); Twitch → `yt-dlp` subtitles; fallback → `faster-whisper` (CPU) on yt-dlp-extracted audio. Returns `[HH:MM:SS] text` lines. |
| Moment selection | `analyzer.identify_moments(transcript)` | Nemotron text endpoint → top five 5-min windows `{start,end,reason}`. |
| Clip analysis | `analyzer.analyze_clips(clip_paths)` | Nemotron video endpoint → per clip `{best moment, caption, virality_score}`. |
| Cutting | `clipper.cut_clips(video_path, timestamps)` | ffmpeg, center-crop to 1080×1920 (9:16), writes `/tmp/clips`. |
| Publishing | `publisher.publish_clips(clip_paths, captions)` | Blotato presigned upload → `/v2/posts` per configured target. |

## 5. Build & deploy

Base `python:3.9`. System deps installed as root, then drop to non-root UID 1000
(HF requirement). Node.js 22, `xz-utils`, `git`, `ripgrep`, `ffmpeg`, `curl`.

**Hermes is installed at runtime, not at build time** (`entrypoint.sh`), because:

- The installer puts code + its managed Node + its managed uv all under
  `$HERMES_HOME`, and we want those on the persistent bucket `/data`.
- `/data` is a **runtime-only mount** — it does not exist during `docker build`.

So `entrypoint.sh` installs Hermes into `/data/.hermes` on boot, idempotently
(`curl … | bash -s -- --skip-setup --skip-browser --non-interactive`), in the
**background** so the web app binds port 7860 immediately. First boot clones; later
boots relink/update. Because `/data` persists, Hermes survives every rebuild.

`ENV HERMES_HOME=/data/.hermes` is set in the Dockerfile.

> History: the original Dockerfile used `… | bash < /dev/null`, which passed no args
> and exited instantly — Hermes was never installed by the image (only manually,
> onto ephemeral disk, lost on rebuild). Do **not** reintroduce a build-time bake.

## 6. Hermes integration (important architecture note)

Hermes Agent registers tools via **MCP** (local stdio or remote HTTP MCP servers
in its config), discovered at startup — **not** by polling a `tools_manifest.json`
over plain HTTP. So:

- `POST /tools/{name}` is for **direct `curl` testing** of each tool.
- To let **Hermes** call these, wrap them as an **MCP server** and register it in
  `/data/.hermes/config.yaml`. `tools_manifest.json` is the contract for that wrapper.
- Hermes state lives under `HERMES_HOME=/data/.hermes` (config `config.yaml`,
  secrets `.env`, managed Node/uv, code) — all on the persistent bucket.

## 7. External services

- **fal** (`fal-client`, `FAL_KEY`): NVIDIA Nemotron 3 Nano Omni. Endpoints
  (verified on fal.ai/nemotron): text `nvidia/nemotron-3-nano-omni`, video
  `nvidia/nemotron-3-nano-omni/video`. ⚠️ video input key `video_url` not
  runtime-verified (`analyzer._VIDEO_INPUT_KEY` is a one-line fix if 422).
- **Blotato** (`requests`, `BLOTATO_API_KEY` header `blotato-api-key`): presigned
  upload `POST https://backend.blotato.com/v2/media/uploads` (→ `presignedUrl` +
  `publicUrl`, then PUT bytes); publish `POST …/v2/posts`. ⚠️ `/v2/posts` is
  **per-account** (`accountId`+`platform`+`target`) — no single "all platforms"
  call. Set `BLOTATO_TARGETS` (env, JSON array) to your connected accounts.
- **Space secrets** (Settings → Variables and secrets): `ANTHROPIC_API_KEY`,
  `FAL_KEY`, `BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Keep
  `FAL_KEY` here as a Space secret; it must **not** be stored inside Hermes' own
  `/data/.hermes` config (see MAINTENANCE.md).

## 8. Local development

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860
```

Create `.env` (gitignored) with the five keys above. Test a tool directly:

```bash
curl -X POST localhost:7860/tools/get_transcript -H 'Content-Type: application/json' \
  -d '{"video_url":"https://youtu.be/..."}'
```

## 9. New machine

Clone the Space (don't zip): `git clone https://huggingface.co/spaces/devproxa/Autoclipping`
→ `code Autoclipping`. Auth with `devproxa` + HF write token. Recreate `.env`
(it's gitignored). Edit → commit → `git push origin main` redeploys.

## 10. Open items

- Set Space secrets `FAL_KEY` and `BLOTATO_API_KEY`; set `BLOTATO_TARGETS`.
- Verify the next rebuild's logs show Hermes installing into `/data` and `GET /`
  flipping `hermes` from `installing` → `installed`.
- Build the **MCP wrapper** so Hermes can call the tools (§6).
- Smoke-test each tool via `POST /tools/{name}` after the rebuild.
- Confirm fal video input key; fill in `BLOTATO_TARGETS`.
