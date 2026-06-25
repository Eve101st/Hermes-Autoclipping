# Autoclipping — Where Things Stand (Plain-English)

*Last updated: June 25, 2026*

## What this project is

Autoclipping is an automation app that runs in the cloud on **Hugging Face Spaces**.
It's packaged with **Docker** (a way to bundle the app so it runs the same
everywhere), and it's set up to be driven by an AI assistant called **Hermes Agent**.

Right now we've finished **Phase 1: the foundation**. Think of it as pouring the
concrete and putting up the frame — the house isn't furnished yet, but the
structure is standing and the lights turn on.

## What's done ✅

- The project lives online at the Space: **devproxa/Autoclipping** (private).
- All the starter files are created and **uploaded** to the Space.
- The app has a simple "are you alive?" page that, when working, replies:
  > "Autoclipping pipeline is live"
- Hermes Agent is set to install automatically when the app builds.
- Secret keys (passwords for the various services) have safe placeholders and are
  kept **out** of the public files.

## What's NOT done yet ⏳

1. **Confirming the build worked.** Uploading the files automatically kicks off a
   "build." We still need to look at the build screen and confirm it finished
   without errors — *especially* the part that installs Hermes Agent, which is the
   most likely thing to trip up.
2. **Adding the real secret keys.** The app currently has placeholders. The real
   keys need to be added in the Space's settings before any real work can happen.
3. **Building the actual features.** Phase 1 is just the skeleton. The real
   logic (turning videos into clips, etc.) comes in Phase 2.

## Your next steps 👉

1. **Check the build.** Go to the Space:
   https://huggingface.co/spaces/devproxa/Autoclipping
   Open the **Logs** tab and look for either a green "Running" status or any red
   error. If you see an error mentioning **Hermes** or **install.sh**, copy it and
   send it over — that's the expected weak spot.
2. **Add your secret keys** in the Space under **Settings → Variables and secrets**:
   `ANTHROPIC_API_KEY`, `FAL_KEY`, `BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`.
3. **When ready, start Phase 2** — the real automation logic.

## Moving to your other computer 💻

You do **not** need to copy this folder by hand. Everything is saved online.
On the new machine, just "download" a fresh copy from the Space (the technical
steps are in `HANDOFF.md`). The only thing that won't come along is the secret-keys
file (`.env`) — that's on purpose, for safety. You'll re-create it from the list
above.

## Where to find the details

- **`CLAUDE.md`** — the single source of truth: architecture, hosting/git, build &
  deploy, the pipeline tools, external services, and open items. (Replaces the old
  `HANDOFF.md`, which was deleted 2026-06-26.)
- **`README.md`** — HF Space config frontmatter + short blurb (kept because the
  frontmatter is required for the Space to build).

---

## 📌 Build notes (2026-06-25) — pending, NOT yet implemented

These are decisions/specs captured for the upcoming **build prompts**. No code for
them has been committed yet. When the build prompts run, build from here; if a
prompt is missing detail, fall back to these notes.

### A. Hermes runtime state (durability still open)

- Hermes Agent **is installed and configured** in the running Space (Dev Mode
  container). Text model in use: **Owl Alpha**.
- Persistent state lives on the mounted **bucket** `devproxa/Autoclipping-storage`
  at **`/data`** — specifically `HERMES_HOME=/data/.hermes` (config at
  `/data/.hermes/config.yaml`, secrets at `/data/.hermes/.env`). These **survive
  rebuilds**.
- ⚠️ The Hermes **binary/code** is currently on the container's **ephemeral** local
  disk (`/home/user/.local/lib/hermes-agent`). It will **vanish on the next
  rebuild/restart**. The credentials/config on `/data` survive, but the binary does
  not.
- **TODO when building:** bake the Hermes install into the `Dockerfile` so every
  build restores the binary, and set `ENV HERMES_HOME=/data/.hermes`. The build's
  current install line no-ops because it lacks `--non-interactive` (the `< /dev/null`
  exits the installer instantly — see build log "DONE 0.2s"). Correct invocation:
  add `xz-utils` to apt, use Node 22 (or keep 20.20.2 — installer accepts
  `^20.19 || >=22.12`), and run:
  `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser --skip-setup --non-interactive`

### A-RESOLVED (2026-06-26) — Hermes build/install fixed via runtime entrypoint

The Section-A plan ("bake install into Dockerfile + `ENV HERMES_HOME=/data/.hermes`")
turned out **not viable** once the installer source was read:

- The old build line `... | bash < /dev/null` passed **no args + empty stdin**, so
  the installer exited instantly (`DONE 0.2s`) — Hermes was never installed by the
  image, only manually onto ephemeral disk. Every rebuild lost it.
- In non-root mode the installer puts **code + managed Node + managed uv all under
  `$HERMES_HOME`** (`$HERMES_HOME/hermes-agent`, `/node`, `/bin/uv`). `/data` is a
  **runtime-only** bucket mount (absent during `docker build`), so baking the
  install with `HERMES_HOME=/data` fails at build, and using a different build-time
  `HERMES_HOME` then switching to `/data` orphans the managed Node/uv.

**Fix shipped:** install Hermes at **container startup into `/data/.hermes`**,
idempotently, via `entrypoint.sh` (runs in the background so the web app + HF health
check come up immediately). Because `/data` persists, Hermes now survives rebuilds
permanently. Changes: new `entrypoint.sh`; `Dockerfile` drops the no-op bake line,
adds `xz-utils`, bumps Node 20→22, sets `ENV HERMES_HOME=/data/.hermes`, runs
`CMD ["./entrypoint.sh"]`; `app.py` health check now **probes** `hermes` on PATH
(`installed`/`installing`) instead of hardcoding it. Installer invoked as:
`curl -fsSL .../install.sh | bash -s -- --skip-setup --skip-browser --non-interactive`.

### B. Clip-analysis step — NVIDIA Nemotron 3 Nano Omni (video) via fal

- **Goal:** a pipeline step that *watches* a source video and returns candidate
  clip moments (it is a multimodal **understanding** model, not a generator).
- **Why it wasn't in Hermes' FAL "video models" list:** fal catalogs it as a
  *Large Language Model*, not a video-generation model, so it's filtered out of the
  video-models view. It is still available on fal.
- **Route:** fal via `fal-client` using `FAL_KEY` (already in `requirements.txt`
  and `config.py`).
- **fal endpoint id:** `nvidia/nemotron-3-nano-omni/video`
- **Inputs:** `prompt` (required, str) and `video_url` (required, str; accepts
  mp4/mov/webm/m4v/gif). ⚠️ `video_url` is the standard fal field name but was **not
  runtime-verified** — confirm against the live schema; if a call returns 422, fix
  the key name.
- **Output:** `output` (str), `finish_reason` (str), `usage` `{input_tokens,
  output_tokens}`.
- **Cost:** ~$0.006 per 1K tokens.
- **Call pattern:**
  `fal_client.subscribe("nvidia/nemotron-3-nano-omni/video", arguments={"prompt": ..., "video_url": ...}, with_logs=False)`
  (fal_client reads `FAL_KEY` from the environment).
- **Blocker:** the `FAL_KEY` secret is **not yet set** on the Space
  (Settings → Variables and secrets).
- A reference implementation (`clip_analysis.py` + a `POST /analyze` endpoint) was
  prototyped and then **reverted on 2026-06-25** per request — rebuild from these
  notes when the build prompts run.

---

## 🛠️ Build (2026-06-25) — Hermes tool modules implemented

Built per the "build the individual tool modules" prompt. New files:

- `tools/transcript.py` — `get_transcript(video_url)`. YouTube →
  youtube-transcript-api (~1s pacing); Twitch → **yt-dlp** subtitle extraction
  (added `yt-dlp` to `requirements.txt`); fallback → faster-whisper (CPU) over
  yt-dlp-extracted audio. Returns `[HH:MM:SS] text` lines.
- `tools/analyzer.py` — `identify_moments(transcript)` (text endpoint
  `nvidia/nemotron-3-nano-omni`) and `analyze_clips(clip_paths)` (video endpoint
  `nvidia/nemotron-3-nano-omni/video`, clips uploaded via `fal_client.upload_file`).
  Both endpoint IDs verified on fal.ai/nemotron; the video input key `video_url`
  is still **not runtime-verified** (`_VIDEO_INPUT_KEY` is a one-line fix if 422).
- `tools/clipper.py` — `cut_clips(video_path, timestamps)` via **ffmpeg**
  (HyperFrames left unused/unverified). Center-crops to 1080×1920, writes `/tmp/clips`.
- `tools/publisher.py` — `publish_clips(clip_paths, captions)` against Blotato.
  Verified endpoints: presigned upload `POST /v2/media/uploads` (→ `presignedUrl`
  + `publicUrl`, then PUT bytes) and `POST /v2/posts`.
- `tools_manifest.json` — contract for all **five** tools.
- `app.py` — added `POST /tools/{tool_name}` bridge (lazy imports per tool).

### ⚠️ Architecture finding — Hermes uses MCP, not a polled manifest

The original plan assumed Hermes reads `tools_manifest.json` and calls tools over
plain HTTP. **It does not.** Hermes Agent discovers tools via **MCP** (local stdio
or remote HTTP MCP servers) registered in its config, at startup. So the
`/tools/{name}` bridge is correct for **direct `curl` testing**, but to let Hermes
actually call these we still need to **wrap them as an MCP server** and register it
in `/data/.hermes/config.yaml`. The manifest now doubles as the source-of-truth
contract for that wrapper. *(Building the MCP wrapper is left for the next build
prompt — not built ahead.)*

### Open items before these run end-to-end
- `FAL_KEY`, `BLOTATO_API_KEY` Space secrets must be set.
- `BLOTATO_TARGETS` must be filled — Blotato's `/v2/posts` is **per-account**
  (`accountId`+`platform`+`target`); there is no single "all platforms" call, so
  `publish_clips` loops over configured targets.
- Smoke-test each tool via `curl -X POST .../tools/<name> -d '{...}'` after the
  rebuild (couldn't run locally — fastapi/deps not installed on this machine).
