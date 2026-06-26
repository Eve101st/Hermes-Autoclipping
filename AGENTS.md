# AGENTS.md — Autoclipping Source of Truth (VPS branch)

> ## 🛑 AGENTS / LLMs: READ THIS FILE FIRST, BEFORE DOING ANYTHING
> This is the canonical source of truth for the **`vps`** branch. Any agent or model
> working here — Claude, Owl Alpha, or any other LLM brought in later — must read
> this file in full before making changes, running commands, or answering about the
> system. Key facts:
> - **This is the VPS branch.** It deploys to a **Tencent VPS via Docker Compose**.
>   The **`main`** branch is the Hugging Face Spaces build — do not mix the two.
>   Why split: HF Spaces and Telegram can't reach each other at the network level,
>   so the Hermes Telegram gateway can't run on HF (§2).
> - **Text model: Owl Alpha**, configured inside Hermes Agent (`hermes model`). There
>   is **no Anthropic key** and no per-task model tiering set up.
> - **Hermes is baked into the image at build time** and seeded into the `/data`
>   named volume on first run (§5). A real VPS filesystem preserves exec bits, so
>   there are **no FUSE / exec-bit / Dev-Mode workarounds** here (those are HF-only,
>   on `main`).
> - **Never `merge main → vps`** — it would drag the HF hosting code back. Cherry-pick
>   shared-file fixes (e.g. `tools/`) between branches instead.
> - **Don't commit or push unless explicitly asked** — the maintainer controls git timing.

Single source of truth for this project. **`PROJECT_STATUS.md`** is the running,
plain-English status log; this file is the durable technical reference.
**`STARTUP_GUIDE.md`** is the deploy/configure runbook. A short `CLAUDE.md` stub
points here so Claude Code auto-loads this file.

**Maintainer:** devproxa (evedarkness18@gmail.com) · **Last updated:** 2026-06-26

---

## 1. What this is

A Docker-based automation pipeline running on a **Tencent VPS** (Docker Compose),
orchestrated by **Hermes Agent** (NousResearch). The pipeline: fetch a video
transcript → pick clip-worthy moments → cut vertical clips → analyze each clip →
publish to socials.

A FastAPI app (`app.py`) serves a health check and a `POST /tools/{name}` bridge
that exposes each pipeline tool for direct testing.

## 2. Hosting & git (read first)

| Property | Value |
|----------|-------|
| Host | Tencent VPS (Docker + Docker Compose) |
| Orchestration | `docker-compose.yml` — `app` (FastAPI + Hermes) + `caddy` (reverse proxy / TLS) |
| Deploy source | a **GitHub** repo (separate account); the VPS clones the `vps` branch from there |
| App port | `7860` (internal; published via Caddy, not bound to the host) |
| TLS / domain | Caddy auto-Let's-Encrypt; configure domain + email in `Caddyfile` |
| Persistent storage | docker **named volume** `hermes-data` mounted at `/data` (`HERMES_HOME=/data/.hermes`) |
| Deploy | `git pull && docker compose up -d --build` |

- **Two branches.** `main` = Hugging Face Spaces build (the `origin` remote IS the
  HF Space). `vps` = this VPS build, deployed from GitHub. They diverge permanently;
  **do not merge `main` into `vps`** (cherry-pick shared fixes instead).
- The VPS pulls from a GitHub repo under a **separate account** from the HF/client
  account. Authenticate that push with the other account's PAT or a dedicated SSH
  key; keep `origin` (the HF Space) untouched.

## 3. Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app: `GET /` health check (probes `hermes` on PATH) + `POST /tools/{tool_name}` bridge. |
| `config.py` | Loads env vars (`.env` / compose `env_file`). Exposes `FAL_KEY`, `BLOTATO_API_KEY`. (Telegram creds are Hermes-owned, not here.) |
| `start.sh` | Container entrypoint: launches the Telegram gateway if configured (background), then execs uvicorn. No install/repair — Hermes is baked in (§5). |
| `mcp_server.py` | MCP server wrapping the five tools so Hermes can call them (spawned by Hermes over stdio). See §6. |
| `Dockerfile` | Image build — `python:3.11` base — bakes Hermes at build time. See §5. |
| `docker-compose.yml` | VPS orchestration: `app` + `caddy`, named volume `hermes-data:/data`, `env_file: .env`. |
| `Caddyfile` | Reverse proxy + auto-TLS config (set domain + email before first deploy). |
| `.env.example` | Template for `.env` (`FAL_KEY`, `BLOTATO_API_KEY`, `BLOTATO_TARGETS`). |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `httpx`, `python-dotenv`, `fal-client`, `requests`, `fastmcp`. |
| `tools/` | Pipeline tool modules — see §4. |
| `tools_manifest.json` | Tool contract (input/output schemas) for the REST bridge; mirrors the MCP tools in `mcp_server.py`. |
| `README.md` | VPS quick-start + branch note. |
| `PROJECT_STATUS.md` | Plain-English status + build-notes log. |
| `STARTUP_GUIDE.md` | VPS deploy + configure runbook. |
| `.env` | Secrets, gitignored — never committed. |

## 4. Pipeline tools (`tools/`)

Plain functions, no framework coupling. Callable directly, via `POST /tools/{name}`,
or via the MCP wrapper.

| Tool | Function | Notes |
|------|----------|-------|
| Transcript | `transcript.get_transcript(video_url)` | YouTube → `youtube-transcript-api` (~1s pacing); Twitch → `yt-dlp` subtitles; fallback → `faster-whisper` (CPU) on yt-dlp-extracted audio. Returns `[HH:MM:SS] text` lines. |
| Moment selection | `analyzer.identify_moments(transcript)` | Nemotron text endpoint → top **ten** windows `{start,end,reason}`, each **≤2 min**, on **sentence boundaries** (see §4a). |
| Clip analysis | `analyzer.analyze_clips(clip_paths)` | Nemotron video endpoint (mp4, ≤1080p, **≤2 min**) → per clip `{best moment, caption, virality_score}`. |
| Cutting | `clipper.cut_clips(video_path, timestamps)` | ffmpeg, center-crop to 1080×1920 (9:16), **2-second lead buffer** (`LEAD_BUFFER_SECONDS`), writes `/tmp/clips`. |
| Publishing | `publisher.publish_clips(clip_paths, captions)` | Blotato presigned upload → `/v2/posts` per configured target; per-target `content` merge (YouTube title/privacyStatus). |

### 4a. Pipeline behaviour spec (agents MUST follow this)

The end-to-end flow Hermes orchestrates over a VOD:

1. **Transcript** — `get_transcript(vod_url)` → timestamped text.
2. **Select 10 cuts** — `identify_moments(transcript)` → the text model (Owl Alpha,
   then Nemotron text) returns **exactly ten** candidate windows, **each ≤2 minutes**
   (target ~115s to leave room for the buffer + the Nemotron 2-min video cap).
3. **Sentence-boundary reasoning (required)** — the model MUST place `start`/`end` on
   **natural sentence boundaries / clear pauses, never mid-sentence**. It inspects the
   transcript line at each boundary; if a sentence is in progress it moves the
   boundary to the sentence start/end, and **confirms this in each window's `reason`**.
4. **Download + cut the VOD** — download the source VOD video (yt-dlp), then
   `cut_clips(video_path, windows)`. Each cut starts **2 seconds early**
   (`LEAD_BUFFER_SECONDS`, clamped at 0) as a safety margin so a clip never opens in
   the middle of a sentence; clips are 9:16 mp4 in `/tmp/clips`.
5. **Analyze** — `analyze_clips(clips)` (Nemotron video) → best 30–90s, caption, score.
6. **Publish** — `publish_clips(clips, captions)` to the Blotato targets (§7).

> Why the buffer + reasoning are belt-and-suspenders: the model is *instructed* to pick
> clean boundaries (step 3), and the cutter *also* pads 2s at the start (step 4), so
> even an imperfect boundary won't clip someone mid-word.

## 5. Build & deploy

Base `python:3.11` (≥3.10 required by `fastmcp`/the MCP SDK; Hermes also prefers
3.11). System deps installed as root, then drop to non-root UID 1000 (hygiene, not
required on a VPS). Node.js 22, `xz-utils`, `git`, `ripgrep`, `ffmpeg`, `curl`.
`CMD ["./start.sh"]`.

**Hermes is baked into the image at build time** (`Dockerfile`):

- The installer puts code + its managed Node + its managed uv all under
  `$HERMES_HOME` (`/data/.hermes`). On a VPS the build filesystem is real, so the
  install runs cleanly during `docker build` (unlike HF, where `/data` is a
  runtime-only FUSE mount that drops the +x bit — none of that applies here).
- Install line:
  `curl -fsSL …/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive`,
  run as the `user` after `mkdir -p /data/.hermes && chown -R user:user /data`.

**Persistence via named-volume seeding.** `docker-compose.yml` mounts the
`hermes-data` named volume at `/data`. The first time the volume is empty, Docker
**seeds it from the image's baked `/data`**; thereafter it persists across rebuilds.
So `hermes model` / `hermes gateway setup` / MCP registration are done **once** and
survive `docker compose up --build`.

> ⚠️ Because a **non-empty** volume is never re-seeded, rebuilding the image with a
> newer Hermes does **not** replace the Hermes already in an existing volume. To
> upgrade Hermes: update it from inside the container, or recreate the `hermes-data`
> volume (then redo the one-time §10 setup). App/tool code lives under `/app` (not on
> the volume), so code changes ship normally via image rebuild.

`start.sh` then: launch the Telegram gateway (`hermes gateway`) in the background if
a token is present in `/data/.hermes`, and exec uvicorn in the foreground.

`ENV HERMES_HOME=/data/.hermes` is set in the Dockerfile.

## 6. Hermes integration (important architecture note)

Hermes Agent registers tools via **MCP** (local stdio or remote HTTP MCP servers
in its config), discovered at startup — **not** by polling a `tools_manifest.json`
over plain HTTP. So:

- `POST /tools/{name}` (uvicorn) is for **direct `curl` testing** of each tool.
- Hermes calls the tools through **`mcp_server.py`** (FastMCP, stdio), which Hermes
  spawns once it's registered in `/data/.hermes/config.yaml`:

  ```yaml
  mcp_servers:
    autoclipping:
      command: /usr/local/bin/python
      args: ["/app/mcp_server.py"]
      enabled: true
      tools:
        include: [get_transcript, identify_moments, cut_clips, analyze_clips, publish_clips]
  ```
  Reload after editing with `/reload-mcp` (or `docker compose restart app`). The
  subprocess inherits the container env (compose `env_file`), which `config.py` reads.
- Hermes state lives under `HERMES_HOME=/data/.hermes` (config `config.yaml`,
  secrets `.env`, managed Node/uv, code) — all on the persistent `hermes-data` volume.

## 7. External services

- **fal** (`fal-client`, `FAL_KEY`): NVIDIA Nemotron 3 Nano Omni. Endpoints +
  schema verified against the fal Nemotron docs: text `nvidia/nemotron-3-nano-omni`
  (`{prompt}` → `{output}`); video `nvidia/nemotron-3-nano-omni/video`
  (`{prompt, video_url}` → `{output}`). **Video input limit: mp4, ≤1080p, ≤2 min** —
  hence `identify_moments` caps windows at 2 min.
- **Blotato** (`requests`, `BLOTATO_API_KEY` header `blotato-api-key`): presigned
  upload `POST https://backend.blotato.com/v2/media/uploads` (→ `presignedUrl` +
  `publicUrl`, then PUT bytes); publish `POST …/v2/posts`. ⚠️ `/v2/posts` is
  **per-account** (`accountId`+`platform`+`target`) — no single "all platforms"
  call. Set `BLOTATO_TARGETS` (env, JSON array) to your connected accounts.
- **LLM (text model):** Owl Alpha via Hermes — **no Anthropic key required**. The
  model is configured inside Hermes (`hermes model`).
- **Telegram:** bot token + allowed users are configured inside Hermes
  (`hermes gateway setup` → `/data/.hermes/.env`), **not** as container env vars.
- **Container env** (`.env` via compose `env_file`): `FAL_KEY`, `BLOTATO_API_KEY`,
  `BLOTATO_TARGETS`. Keep `FAL_KEY` here; it must **not** be stored inside Hermes'
  own `/data/.hermes` config.

## 8. Local development

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in keys
uvicorn app:app --host 0.0.0.0 --port 7860
```

Test a tool directly:

```bash
curl -X POST localhost:7860/tools/get_transcript -H 'Content-Type: application/json' \
  -d '{"video_url":"https://youtu.be/..."}'
```

## 9. New machine / fresh VPS

```bash
git clone <github-repo> autoclipping && cd autoclipping && git checkout vps
cp .env.example .env        # fill in keys (gitignored, not in the clone)
# edit Caddyfile (domain + email)
docker compose up -d --build
```

Then the one-time Hermes setup (§10). Update later with
`git pull && docker compose up -d --build`.

## 10. Hermes manual setup (one-time, inside the container)

Done once; persists on the `hermes-data` volume. After this, restart the app and
`start.sh` auto-launches the Telegram gateway.

```bash
# 1. LLM provider + models (interactive). Text model is Owl Alpha via Hermes — no
#    Anthropic key needed. Confirm/select Owl Alpha here.
docker compose exec app hermes model

# 2. Telegram (interactive): paste TELEGRAM_BOT_TOKEN + your numeric user ID.
#    Writes TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_USERS to /data/.hermes/.env.
docker compose exec app hermes gateway setup

# 3. Register the tools: add the mcp_servers block from §6 to
#    /data/.hermes/config.yaml (e.g. `docker compose exec app vi /data/.hermes/config.yaml`).

# 4. Apply + run the bot:
docker compose restart app
```

Confirm tools are visible to Hermes with `docker compose exec app hermes tools`.

## 11. Open items

- Provision the Tencent VPS (Docker + Compose), domain DNS, and open ports 80/443.
- Create the GitHub repo (separate account), push `main` + `vps`, set it as the
  VPS's clone source. Keep `origin` = the HF Space untouched.
- Set `.env` (`FAL_KEY`, `BLOTATO_API_KEY`, `BLOTATO_TARGETS`); set `Caddyfile`
  domain + email.
- Verify the first build bakes Hermes and `GET /` reports `hermes: installed`.
- Do the §10 one-time Hermes setup (model, Telegram, MCP registration).
- Confirm `mcp_server.py` runs under Hermes (verify the `@mcp.tool`/`mcp.run()`
  FastMCP API against the installed `fastmcp` version) and `hermes tools` lists all five.
- Smoke-test each tool via `POST /tools/{name}`; fill `BLOTATO_TARGETS`.
- Confirm TikTok's exact `privacyLevel` enum value against Blotato's docs.
- **Implemented:** 10 windows + 2-min cap + sentence-boundary reasoning (§4a);
  clipper 2s lead buffer (`LEAD_BUFFER_SECONDS`); YouTube publishing via per-target
  `content` merge.
- Open product question: the pipeline publishes the cut *window* clips. To publish
  only the 30-90s "best moment" from `analyze_clips`, Hermes must re-cut (call
  `cut_clips` again with those timestamps) before `publish_clips`.
- Pipeline gap: `cut_clips` needs the VOD **video** downloaded locally first
  (yt-dlp); there is no dedicated download tool yet — Hermes/the orchestrator must
  fetch the VOD before cutting (§4a step 4).
