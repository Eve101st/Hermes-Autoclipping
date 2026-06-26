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
   `FAL_KEY`, `BLOTATO_API_KEY`. (No Anthropic key — the text model is Owl Alpha via
   Hermes. Telegram bot token + chat ID are set in `hermes gateway setup`, not here.)
3. **When ready, start Phase 2** — the real automation logic.

## Moving to your other computer 💻

You do **not** need to copy this folder by hand. Everything is saved online.
On the new machine, just "download" a fresh copy from the Space (the technical
steps are in `HANDOFF.md`). The only thing that won't come along is the secret-keys
file (`.env`) — that's on purpose, for safety. You'll re-create it from the list
above.

## Where to find the details

- **`AGENTS.md`** — the single source of truth (formerly `CLAUDE.md`, renamed
  2026-06-26 so any LLM reads it first): architecture, hosting/git, build & deploy,
  the pipeline tools, external services, and open items. A small `CLAUDE.md` stub
  points to it. (Replaces the old `HANDOFF.md`, deleted 2026-06-26.)
- **`STARTUP_GUIDE.md`** — step-by-step deploy + configure runbook, written for both
  technical and non-technical readers.
- **`README.md`** — HF Space config frontmatter + short blurb (kept because the
  frontmatter is required for the Space to build).

---

## 🚀 Phase 3 (2026-06-26) — Hermes wiring built

Built per the Phase 3 prompt. Code shipped; the LLM/Telegram/tool-registration
config is **manual in the dev terminal** (see `AGENTS.md` §10) and the end-to-end
test is deferred (user plugs in all API keys after build).

- `start.sh` (replaces `entrypoint.sh`) — restore Hermes into `/data` (bg) →
  launch `hermes gateway` if Telegram is configured in Hermes `/data` (bg) → exec uvicorn (fg).
  `Dockerfile` `CMD` now runs `start.sh`; base bumped `python:3.9 → 3.11` (fastmcp
  needs ≥3.10); added `fastmcp` to `requirements.txt`.
- `mcp_server.py` (FastMCP, stdio) — the **real tool-registration mechanism**.
  Hermes spawns it via an `mcp_servers:` block in `config.yaml` (§6/§10). The
  prompt's "register http://localhost:7860/tools" does **not** work — Hermes speaks
  MCP, and the REST bridge isn't MCP.

⚠️ Prompt assumptions corrected via the live docs:
- **Telegram** — Hermes has a **built-in** gateway (`hermes gateway`, python-telegram-bot);
  no custom webhook bridge needed. Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`.
- **Models** — `hermes model` picker; main model + per-task `auxiliary:` overrides
  (not a simple/medium/complex tier system). Haiku-for-parsing → an auxiliary override.
- **Tool registration** — MCP (`mcp_servers` in `config.yaml`), `/reload-mcp` to apply.

Still open: verify the FastMCP `@mcp.tool`/`mcp.run()` API against the installed
version at runtime; confirm `hermes tools` lists all five after registration.

### 🧱 Hurdle (2026-06-26): Hermes `cannot execute: Permission denied` on /data

**Symptom:** `hermes` → `/data/.hermes/hermes-agent/venv/bin/hermes: cannot execute:
Permission denied`.

**First theory (WRONG):** `/data` mounted `noexec`. Ruled out — `findmnt /data`
shows an `hf-mount` FUSE mount `rw,nosuid,nodev,…` with **no `noexec`**, and a
`chmod +x` test script ran fine from `/data`.

**Actual cause:** the HF persistent store is a FUSE mount that does **not preserve
the execute bit** when the installer writes Hermes' venv scripts — they land `0644`,
so the launcher can't `exec` them.

**Fix (shipped, commit `98393fa`):** `start.sh` → `repair_perms()` runs
`chmod -R u+x` on `…/venv/bin`, `bin`, `node/bin` after the install step, on every
boot (idempotent).

**Second wrinkle — Dev Mode skips `start.sh`:** in HF **Dev Mode** the container
hands you a terminal instead of running the image `CMD`, so `start.sh` (install +
perms-repair + gateway) does **not** run; the `hermes` symlink in ephemeral
`/home/user/.local/bin` is also wiped by a factory reboot. In a dev terminal,
restore it manually (single line):

```bash
chmod -R u+x /data/.hermes/hermes-agent/venv/bin /data/.hermes/bin /data/.hermes/node/bin && ln -sf /data/.hermes/hermes-agent/venv/bin/hermes "$HOME/.local/bin/hermes" && export PATH="$HOME/.local/bin:$PATH" && hermes --version
```

If the venv is stale, re-run the installer (idempotent):

```bash
export HERMES_HOME=/data/.hermes; curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive
```

Production (Dev Mode **off**) runs `start.sh` and does all of this automatically.
Also note: the running image is now `python:3.11` (3.9 → 3.11 for fastmcp); confirm
with `python --version` after a factory reboot. Full runbook: **`STARTUP_GUIDE.md`**.

---

## 🌿 Branch split (2026-06-26) — VPS retarget, pending build prompt

**Why two branches:** Hugging Face Spaces and Telegram cannot reach each other at
the network level (the HF egress / Telegram is blocked), so the Hermes Telegram
gateway can't run on HF. Decision:

- **`main`** — stays the **Hugging Face Spaces** build (current `/data` FUSE setup).
- **`vps`** — retargeted to deploy on a **Tencent VPS**, where the Telegram gateway
  can actually reach the network. (`vps` has no upstream remote configured yet.)

### Target VPS architecture (decided 2026-06-26, all defaults chosen)

- **Orchestration:** Docker Compose (`docker-compose.yml`) — closest to the current
  Dockerfile; easy restarts/logs.
- **Persistence:** Docker **named volume** mounted at `/data`, keep
  `HERMES_HOME=/data/.hermes`. Survives rebuilds, no host-path coupling.
- **Networking:** **reverse proxy + TLS** (Caddy or nginx) terminating HTTPS on a
  domain, proxying to uvicorn on `7860` (kept internal).
- **Hermes install:** **bake into the Docker image at build time** — now viable
  because a real VPS filesystem/volume preserves exec bits and symlinks.

### ✅ VPS file prep DONE (2026-06-26)

Files retargeted to the VPS architecture (not yet committed/pushed). What changed:
- `start.sh` — stripped `repair_venv`/`repair_perms` + runtime installer; now just
  gateway (bg) + uvicorn (fg).
- `Dockerfile` — bakes Hermes at build into `/data/.hermes` (relies on docker
  named-volume seeding for persistence); dropped FUSE chmod/repair reasoning.
- `docker-compose.yml` (NEW) — `app` + `caddy`, `hermes-data:/data` volume,
  `env_file: .env`, 7860 internal.
- `Caddyfile` (NEW) — reverse proxy + auto-TLS, placeholder `example.com`/email.
- `.env.example` (NEW) — `FAL_KEY`/`BLOTATO_API_KEY`/`BLOTATO_TARGETS`.
- `config.py`, `app.py` — comments retargeted (env_file / baked Hermes).
- `README.md`, `STARTUP_GUIDE.md`, `AGENTS.md` — rewritten for VPS deploy.
- `.gitignore`/`.dockerignore` — updated.
- **Deleted** `fix-hermes.sh` (HF Dev-Mode-only).

Still needs the user: provision the VPS, create the GitHub repo + push, fill
`.env` + `Caddyfile` domain, then the one-time §10 Hermes setup. Commit/push held
until explicitly asked.

### What the VPS retarget changed (original plan — vs the old HF `vps` branch)

These are the HF-Spaces-isms that were removed/retargeted (now done, above).

1. **`start.sh` — delete the FUSE workarounds.** Remove `repair_venv()` and
   `repair_perms()` entirely (they only existed for HF's `/data` FUSE mount). Remove
   the runtime `ensure_hermes()` installer if baking into the image (below). What
   remains: export env → `start_gateway` (background) → `exec uvicorn` (foreground).
2. **`Dockerfile` — bake Hermes at build time.** Install via
   `curl … install.sh | bash -s -- --skip-setup --skip-browser --non-interactive`
   during build (FS now preserves +x, so no post-install chmod needed). Keep
   `xz-utils`, Node 22, ffmpeg, ripgrep. `useradd -u 1000` is optional on a VPS —
   keep for non-root hygiene. Persistent **config/secrets** still live on the named
   volume at `/data/.hermes` so they survive rebuilds even though the binary is baked.
3. **`docker-compose.yml` — new file.** App service (build from Dockerfile), named
   volume → `/data`, `env_file: .env` for `FAL_KEY`/`BLOTATO_API_KEY`,
   `restart: unless-stopped`, expose `7860` to the proxy only. Add the reverse-proxy
   service (Caddy is simplest for auto-TLS) or document an external nginx.
4. **`config.py` / `README.md` — drop HF wording.** "Space secrets" → `.env` /
   compose `env_file`. Remove README HF frontmatter (`sdk: docker`, `app_port`) and
   the "clone the HF Space" instructions; replace with VPS deploy (git pull +
   `docker compose up -d --build`).
5. **Port 7860** can stay (internal, behind proxy) — no need to renumber.
6. **`AGENTS.md`** — add a VPS deployment section / note that `vps` ≠ `main` hosting.

Open question for build time: where does the Telegram token get set on the VPS?
Still via `hermes gateway setup` writing to `/data/.hermes` (now that the gateway
can reach Telegram), so the named volume must exist before that runs.

### Branch state & deploy source (confirmed 2026-06-26)

- There is **one** `vps` branch only. It sits on the **same commit as `main`**
  (`8c340d3`, 0 divergence) with **no remote** — i.e. it's a clean copy of `main`
  with no VPS-specific commits yet. Nothing to reconcile or delete.
- **Deploy source = a new GitHub repo.** The only current remote (`origin`) is the
  HF Space and must NOT be the VPS's source. Plan: create a GitHub repo, push both
  `main` and `vps` there, and the Tencent VPS clones the `vps` branch from GitHub.
  (Not done yet — pushing to a new public remote is an outward action; do it when
  running the build prompt / on explicit go-ahead.)

### Cleanup principle: strip the hosting layer, keep the pipeline

Safe to remove HF-only code on `vps` because `main` retains it. **Remove:**
`repair_venv`/`repair_perms` + runtime-install logic in `start.sh`; README HF
frontmatter (`sdk: docker`, `app_port`) + "clone the HF Space" section; "Space
secrets" wording in `config.py`/README; `useradd -u 1000` optional (keep only for
non-root hygiene). **Keep (shared, NOT HF-specific):** all of `tools/`,
`mcp_server.py`, `app.py` tool bridge + health check, `config.py` keys,
`requirements.txt`, `tools_manifest.json`.

⚠️ Once `vps` diverges, do **NOT** `merge main → vps` (it drags HF code back).
Cherry-pick shared-file fixes (e.g. a `tools/` bug fix) between branches instead.

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
