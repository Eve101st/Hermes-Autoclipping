# AGENTS.md — Autoclipping Source of Truth

> ## 🛑 AGENTS / LLMs: READ THIS FILE FIRST, BEFORE DOING ANYTHING
> This is the canonical source of truth. Any agent or model working here — Claude,
> Owl Alpha, or any other LLM brought in later — must read this file in full before
> making changes, running commands, or answering about the system. Key facts:
> - **Text model: Owl Alpha**, configured inside Hermes Agent (`hermes model`). There
>   is **no Anthropic key** and no per-task model tiering set up.
> - **Hosting:** a Hugging Face **Space**; `git push origin main` redeploys. The remote
>   IS the Space — **never push to GitHub** (§2).
> - **Hermes lives on persistent `/data`**, installed at runtime not build time (§5).
>   The `/data` FUSE mount drops the +x bit, and Dev Mode skips `start.sh` — read §5
>   and the Dev-Mode note before touching Hermes.
> - **Don't commit or push unless explicitly asked** — the maintainer controls git timing.

Single source of truth for this project. **`PROJECT_STATUS.md`** is the running,
plain-English status log; this file is the durable technical reference.
**`STARTUP_GUIDE.md`** is the deploy/configure runbook. `README.md` exists only to
carry the Hugging Face Space config frontmatter (do not delete it). A short
`CLAUDE.md` stub points here so Claude Code auto-loads this file.

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
| `config.py` | Loads env vars (`.env` locally / Space secrets in prod). Exposes `FAL_KEY`, `BLOTATO_API_KEY`. (Telegram creds are Hermes-owned, not here.) |
| `start.sh` | Container entrypoint: restores Hermes into `/data` (background), launches the Telegram gateway if configured, then execs uvicorn. |
| `fix-hermes.sh` | Dev-Mode helper: re-link + repair the `hermes` command after a VS Code/dev reload **without** reinstalling. `source /app/fix-hermes.sh`. See §5 Dev-Mode note. |
| `mcp_server.py` | MCP server wrapping the five tools so Hermes can call them (spawned by Hermes over stdio). See §6. |
| `Dockerfile` | Image build — `python:3.11` base — see §5. |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `httpx`, `python-dotenv`, `fal-client`, `requests`, `fastmcp`. |
| `tools/` | Pipeline tool modules — see §4. |
| `tools_manifest.json` | Tool contract (input/output schemas) for the REST bridge; mirrors the MCP tools in `mcp_server.py`. |
| `README.md` | **HF Space config frontmatter** (`sdk: docker`, `app_port: 7860`) + short blurb. Mandatory for the Space to build. |
| `PROJECT_STATUS.md` | Plain-English status + build-notes log. |
| `STARTUP_GUIDE.md` | Deploy + configure runbook (mixed technical/non-technical audience). |
| `.env` | Secrets, gitignored — never committed. |

## 4. Pipeline tools (`tools/`)

Plain functions, no framework coupling. Callable directly, via `POST /tools/{name}`,
or (eventually) via an MCP wrapper.

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
3.11). System deps installed as root, then drop to non-root UID 1000 (HF
requirement). Node.js 22, `xz-utils`, `git`, `ripgrep`, `ffmpeg`, `curl`.
`CMD ["./start.sh"]`.

**Hermes is installed at runtime, not at build time** (`start.sh`), because:

- The installer puts code + its managed Node + its managed uv all under
  `$HERMES_HOME`, and we want those on the persistent bucket `/data`.
- `/data` is a **runtime-only mount** — it does not exist during `docker build`.

So `start.sh` installs Hermes into `/data/.hermes` on boot, idempotently
(`curl … | bash -s -- --skip-setup --skip-browser --non-interactive`), in the
**background** so the web app binds port 7860 immediately. First boot clones; later
boots relink/update. Because `/data` persists, Hermes survives every rebuild. If
Telegram has been configured in Hermes (token present in `/data/.hermes`),
`start.sh` then launches the Telegram gateway (`hermes gateway`) in the background;
uvicorn runs in the foreground so the Space stays "Running" even before Hermes is
configured.

> **`/data` is a FUSE mount (`hf-mount`)** — it is `rw` and exec-capable (NOT
> `noexec`), but it does **not preserve the +x bit** when the installer writes
> Hermes' venv scripts, so `hermes` fails with "cannot execute: Permission denied".
> `start.sh`'s `repair_perms` re-applies `chmod -R u+x` to Hermes' `…/venv/bin`,
> `bin`, and `node/bin` on every boot (idempotent) to fix this.

> **Dev Mode does NOT run `start.sh`.** It hands you a terminal instead of running
> the image `CMD`, and reloading the web VS Code resets the ephemeral `/home/user`
> — which wipes the `hermes` symlink + PATH, so `hermes` becomes "not found". The
> real install on `/data` is fine; **do NOT reinstall** (it often fails over the
> FUSE mount). Instead relink in one command: **`source /app/fix-hermes.sh`**. On a
> normal (Dev Mode off) boot, `start.sh` handles all of this automatically.

`ENV HERMES_HOME=/data/.hermes` is set in the Dockerfile.

> History: the original Dockerfile used `… | bash < /dev/null`, which passed no args
> and exited instantly — Hermes was never installed by the image (only manually,
> onto ephemeral disk, lost on rebuild). Do **not** reintroduce a build-time bake.

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
  Reload after editing with `/reload-mcp`. The subprocess inherits the container
  env (Space secrets), which `config.py` reads.
- Hermes state lives under `HERMES_HOME=/data/.hermes` (config `config.yaml`,
  secrets `.env`, managed Node/uv, code) — all on the persistent bucket.

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
  model is configured inside Hermes (`hermes model`), not via a Space secret.
- **Telegram:** bot token + allowed users are configured inside Hermes
  (`hermes gateway setup` → `/data/.hermes/.env`), **not** as Space secrets.
- **Space secrets** (Settings → Variables and secrets): `FAL_KEY`,
  `BLOTATO_API_KEY`. Keep `FAL_KEY` here as a Space secret; it must **not** be
  stored inside Hermes' own `/data/.hermes` config.

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

## 10. Hermes manual setup (HF dev-mode terminal)

Done once in the dev terminal; persists on `/data`. After this, restart the Space
and `start.sh` auto-launches the Telegram gateway.

```bash
# 1. LLM provider + models (interactive). Text model is Owl Alpha via Hermes — no
#    Anthropic key needed. Confirm/select Owl Alpha here. Per-task overrides (if any)
#    go under `auxiliary:` in config.yaml; Hermes uses per-task auxiliary routing,
#    not simple/medium/complex tiers.
hermes model

# 2. Telegram (interactive): paste TELEGRAM_BOT_TOKEN + your numeric user ID.
#    Writes TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_USERS to /data/.hermes/.env.
hermes gateway setup

# 3. Register the tools: add the mcp_servers block from §6 to
#    /data/.hermes/config.yaml, then reload (or restart the Space).
hermes   # then in-session: /reload-mcp

# 4. Run the bot (start.sh does this automatically on restart once token is set):
hermes gateway
```

Confirm tools are visible to Hermes with `hermes tools`.

## 11. Open items

- Set Space secrets (`FAL_KEY`, `BLOTATO_API_KEY`); set `BLOTATO_TARGETS`. (No
  Anthropic key — text model is Owl Alpha. Telegram creds go in `hermes gateway setup`.)
- Verify the next rebuild's logs show Hermes installing into `/data` and `GET /`
  flipping `hermes` from `installing` → `installed`.
- Do the §10 manual Hermes setup (model, Telegram, MCP registration).
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
