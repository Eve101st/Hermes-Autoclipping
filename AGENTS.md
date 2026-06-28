# AGENTS.md — Autoclipping Source of Truth (VPS branch)

> ## 🛑 AGENTS / LLMs: READ THIS FILE FIRST, BEFORE DOING ANYTHING
> This is the canonical source of truth for the **`vps`** branch. Any agent or model
> working here — Claude, Owl Alpha, or any other LLM brought in later — must read this
> file in full before making changes, running commands, or answering about the system.
> Key facts:
> - **This is a bare-metal deployment.** Everything runs as **native `systemd` services
>   on one Ubuntu 22.04 VPS**, as a single Linux user, on one real filesystem. There is
>   **no Docker, no container, no reverse proxy** anywhere in this project — not in
>   development, not in production. If you see Docker/Compose/Caddy references in old git
>   history or memory, they are obsolete.
> - **Text model: Owl Alpha**, configured inside Hermes Agent (`hermes model`), served
>   via **OpenRouter** (`openrouter/owl-alpha`). There is **no Anthropic key**. The
>   OpenRouter account is **free-tier only (no credits)** — which is why anything paid
>   (image **vision**) runs through **fal** instead (§8).
> - **A separate branch targets a different, managed host** and shares only the pipeline
>   code. **Never `merge` that branch into `vps`** — cherry-pick shared `tools/` fixes
>   instead.
> - **Don't commit or push unless explicitly asked** — the maintainer controls git timing.
> - **Host/account specifics (IP, SSH user, repo URL, bot handle, account names) live in
>   `INTERNAL.md` (gitignored), NOT here.** Keep this file safe to publish: no IPs, no
>   secrets, no personal info.

`README.md` is the public deploy + usage guide; this file is the durable technical
reference. `PROJECT_STATUS.md` (running status log) and `INTERNAL.md` (host/account
specifics) are **gitignored, local-only**. A short `CLAUDE.md` stub points here so
Claude Code auto-loads this file.

**Last updated:** 2026-06-28 · Host/account details: see `INTERNAL.md` (gitignored).

---

## 1. What this is

An automation pipeline that turns a long video (a VOD or a Telegram upload) into short
vertical clips and publishes them. It is orchestrated by **Hermes Agent**
(NousResearch), which the operator drives from **Telegram**. The pipeline: fetch a
transcript → pick clip-worthy moments → cut vertical clips → analyze each clip → (edit —
not built yet) → publish to socials.

The pipeline logic lives in plain Python tool modules (`tools/`) exposed to Hermes as
**MCP tools** (`mcp_server.py`). Hermes calls tools **only** over MCP — there is no web
server and no REST bridge.

## 2. Hosting & layout (read first)

Everything is native on one Ubuntu 22.04 VPS, run by a single Linux user (referred to
here as the **run user**; the concrete username + VPS IP are in `INTERNAL.md`). Four
`systemd` services, all as the run user so files written by one are readable by another
(no permission split):

| systemd service | What it does |
|-----------------|--------------|
| `tor` (distro pkg) | Loopback SOCKS5 on `127.0.0.1:9050` — the transcript proxy (scoped to transcript fetching only, §7). |
| `telegram-bot-api` | Self-hosted Telegram Bot API server, `--local`, on `127.0.0.1:8081`. Raises the bot upload cap **20 MB → 2 GB** and writes uploads to disk at `/var/lib/telegram-bot-api/` (§7). Built from source (native glibc binary). |
| `fal-vision-proxy` | Tiny loopback auth-rewrite proxy on `127.0.0.1:8089` so Hermes' vision can reach fal's OpenAI-compatible endpoint (§8). |
| `hermes-gateway` | `hermes gateway` — the Telegram gateway (outbound long-poll, no inbound port). Spawns `mcp_server.py` over stdio for the tools. |

| Path | Purpose |
|------|---------|
| `/opt/autoclipping` | The repo clone (`vps` branch), owned by the run user. |
| `/opt/autoclipping/.venv` | Python venv (python3.10) for the pipeline tools. |
| `~/.hermes` | Hermes Agent install + state: `config.yaml`, secrets `.env`, managed Node/uv, and the agent code under `~/.hermes/hermes-agent`. |
| `/var/lib/telegram-bot-api` | Where the Bot API server writes uploads. Owned by the run user → Hermes reads them directly. |

- **Transport is outbound long-polling.** `hermes gateway` reaches Telegram outbound, so
  there is **no inbound port, no TLS, and no domain** to manage.
- **Deploy** = clone the repo to `/opt/autoclipping`, run `deploy/install.sh` (builds &
  installs everything), then the one-time Hermes setup (§10). Details in `README.md`.
- A separate branch targets a different managed host; keep the remotes distinct and
  **never push `vps` code to that remote** (concrete remotes/URLs are in `INTERNAL.md`).

## 3. Files

| File | Purpose |
|------|---------|
| `config.py` | Loads env vars from the process env. Exposes `FAL_KEY`, `BLOTATO_API_KEY`. (Telegram creds are Hermes-owned, not here.) |
| `mcp_server.py` | FastMCP **stdio** server wrapping the six pipeline tools so Hermes can call them. The single tool surface (§6). |
| `scripts/call_tool.py` | Manual single-tool test harness — import + call a tool directly with the same env the MCP server gets. Replaces any web/curl test path. |
| `requirements.txt` | `youtube-transcript-api`, `yt-dlp`, `faster-whisper`, `httpx`, `python-dotenv`, `fal-client`, `requests`, `fastmcp`. (No web framework.) |
| `tools/` | Pipeline tool modules — see §4. |
| `deploy/install.sh` | Idempotent host bootstrap: apt deps, python3.10 venv, Tor config, builds `telegram-bot-api` from source, installs the systemd units. Does **not** start services or run Hermes setup. |
| `deploy/fal-vision-proxy.py` | Loopback `Bearer`→`Key` auth-rewrite proxy for fal vision (§8). |
| `deploy/systemd/*.service` | `telegram-bot-api.service`, `hermes-gateway.service`, `fal-vision-proxy.service`. |
| `.env.example` | Template for the bot-api credentials file (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`). |
| `README.md` | Public deploy + usage guide. |
| `PROJECT_STATUS.md` | Plain-English status + build-notes log — **gitignored, local-only**. |
| `INTERNAL.md` | Host/account specifics (IP, run user, repo URL, bot handle) — **gitignored, local-only**. |
| `.env` | Secrets, gitignored — never committed. |

## 4. Pipeline tools (`tools/`)

Plain functions, no framework coupling. Callable directly, via `scripts/call_tool.py`,
or via the MCP wrapper. **Six** tools:

| Tool | Function | Notes |
|------|----------|-------|
| Transcript | `transcript.get_transcript(video_url)` | `video_url` is a YouTube/Twitch URL **or a local file path** (e.g. a Telegram upload). YouTube → `youtube-transcript-api` (~1s pacing); Twitch → `yt-dlp` subtitles; fallback / local file → `faster-whisper` (CPU). Returns `[HH:MM:SS] text` lines. |
| Moment selection | `analyzer.identify_moments(transcript)` | Nemotron text endpoint → top **ten** windows `{start,end,reason}`, each **≤2 min**, on **sentence boundaries** (§4a). |
| Clip analysis | `analyzer.analyze_clips(clip_paths)` | Nemotron video endpoint (mp4, ≤1080p, **≤2 min**) → per clip `{best moment, caption, virality_score}`. |
| Cutting | `clipper.cut_clips(video_path, timestamps)` | `video_path` is a **local video file (a Telegram upload)** — ffmpeg center-crops each window to 1080×1920 (9:16), **2-second lead buffer** (`LEAD_BUFFER_SECONDS`). Writes `/tmp/clips`. Audio+video stay together. **No URL download** — source videos arrive as uploads (§7). |
| Publishing | `publisher.publish_clips(clip_paths, captions)` | Blotato presigned upload → `/v2/posts` per configured target; per-target `content` merge (YouTube title/privacyStatus). |
| Cleanup | `cleanup.cleanup_files()` | Frees disk: deletes stored uploads/transcripts + generated clips (`/tmp/clips`, the Hermes upload cache, the Bot API server's downloads). Returns `{files_deleted, freed_mb, locations}`. Triggered by `/cleanup`. |

### 4a. Pipeline behaviour spec (agents MUST follow this)

The end-to-end flow Hermes orchestrates over a VOD:

1. **Transcript** — `get_transcript(source)` → timestamped text. `source` is the Telegram
   **upload** (transcribed with whisper) or a YouTube/Twitch **URL** (cheap transcript via
   the API). The video to clip is always the **upload** (steps 4/6).
2. **Select 10 cuts** — `identify_moments(transcript)` → the text model (Owl Alpha, then
   Nemotron text) returns **exactly ten** candidate windows, **each ≤2 minutes** (target
   ~115s to leave room for the buffer + the Nemotron 2-min video cap).
3. **Sentence-boundary reasoning (required)** — the model MUST place `start`/`end` on
   **natural sentence boundaries / clear pauses, never mid-sentence**, and **confirm this
   in each window's `reason`**.
4. **Cut the upload** — `cut_clips(upload_path, windows)`: ffmpeg center-crops each window
   out of the uploaded local video file to 9:16. Each cut starts **2 seconds early**
   (`LEAD_BUFFER_SECONDS`, clamped at 0). Clips are 9:16 mp4 in `/tmp/clips`. (Source
   videos are uploaded to the bot — there is no URL download, §7.)
5. **Analyze (Nemotron, re-evaluate the 10)** — `analyze_clips(clips)` watches all ten
   ≤2-min clips and, for **each**, selects the single best **30–60s** moment plus a
   caption and virality score. The full 2-min clip is the analysis *input*; the 30–60s
   best moment is the *output* that gets published.
6. **Re-cut to the best moment** — `cut_clips(upload_path, best_moments)` with the 30–60s
   timestamps from step 5 → the final short clips.
7. **Edit (HyperFrames, orchestrated by Owl Alpha) — 🔨 NOT BUILT YET (§4c).** Add
   TikTok-style word-by-word captions (§4b), styled to match the clip's vibe. ffmpeg
   grabs sample frames → Owl Alpha **visually reasons** the vibe (via the vision model,
   §8) → caption style chosen → HyperFrames renders captions onto the clip. Music is
   added manually for now.
8. **Approval gate** — present the finished clips with virality scores + captions and
   **wait for the operator to approve** which to post. Do not auto-publish.
9. **Publish** — on approval, `publish_clips(clips, captions)` to the Blotato targets (§7).

> Why the buffer + reasoning are belt-and-suspenders: the model is *instructed* to pick
> clean boundaries (step 3), and the cutter *also* pads 2s at the start (step 4), so even
> an imperfect boundary won't clip someone mid-word.

### 4b. TikTok caption / editing spec (for the §4c editing build)

- **Word-by-word / 2–3-word "karaoke" reveal**, synced to speech (Whisper word-level
  timings). Static full-sentence subtitles are dated.
- **Font:** bold/UPPERCASE sans-serif — Montserrat Bold, Bebas Neue, Impact, or TikTok Sans.
- **Contrast:** white or yellow fill + heavy black outline/stroke; ≥4.5:1 contrast.
- **Vibe highlight:** one key word per phrase popped in a vibe color (yellow/red/green),
  chosen from the ffmpeg-frame visual reasoning (hype / emotional / educational / funny).
- **Placement:** lower-middle third. At 1080×1920, caption band ≈ y 1200–1300px; keep
  clear of the bottom ~370px (platform UI).
- **Timing:** ~20–27 chars max on screen, short min-duration per cue; fast cadence.

### 4c. Editing stage build (HyperFrames) — NOT BUILT, for a future build prompt

What the editing stage needs (no code yet — do not build ahead of a build prompt):

- Install **HyperFrames** + headless Chromium (render path); Node is already present
  under Hermes' managed runtime.
- **Word-level transcription** of each 30–60s clip for caption timing.
- **ffmpeg frame capture** → feed frames to the vision model (§8) for visual reasoning
  about the clip's vibe → pick caption style per §4b.
- A **HyperFrames captions composition** (clip + word timings + style → final captioned mp4).
- **Orchestration wiring:** a new MCP tool (e.g. `edit_clip`) or Owl Alpha shell-driving
  the HyperFrames CLI, slotted between re-cut (step 6) and approval (step 8).
- **Music:** deferred — added manually; a shared music folder may come later.

## 5. Build & deploy (bare metal)

`deploy/install.sh` does the whole host bootstrap, idempotently, as a sudo-capable run
user from a checkout at `/opt/autoclipping`:

1. **apt deps** — `python3.10` + venv + pip, `ffmpeg`, `git`, `ripgrep`, `curl`,
   `xz-utils`, `ca-certificates`, `tor`; Node.js 22 (NodeSource) and `uv` for Hermes.
2. **Tor** — writes `/etc/tor/torrc` (loopback SOCKS5 on `127.0.0.1:9050`).
3. **venv** — `/opt/autoclipping/.venv` + `pip install -r requirements.txt`.
4. **telegram-bot-api** — built from source (tdlib) to a native glibc binary at
   `/usr/local/bin/telegram-bot-api`. (The compile is RAM-hungry; on a 2-core/≤4 GB box
   add swap and use `-j2`.)
5. **systemd units** — installs `telegram-bot-api.service`, `hermes-gateway.service`,
   `fal-vision-proxy.service` (does **not** enable/start them — that's the cutover step).

Hermes itself is installed natively via its own installer
(`curl -fsSL …/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive`),
which puts the agent code + managed Node + managed uv under `~/.hermes`. The pipeline
venv (python3.10) is separate from Hermes' own managed runtime.

After install, do the one-time Hermes setup (§10), then enable + start the services.
Update later with `git pull` in `/opt/autoclipping` + `sudo systemctl restart
hermes-gateway` (and rebuild the bot-api binary only if its source changed).

## 6. Hermes integration (architecture note)

Hermes registers tools via **MCP** (local stdio servers in its config), discovered at
startup. `mcp_server.py` (FastMCP, stdio) is the single tool surface — Hermes spawns it
once it's registered in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  autoclipping:
    command: /opt/autoclipping/.venv/bin/python
    args: ["/opt/autoclipping/mcp_server.py"]
    enabled: true
    env:                      # REQUIRED — stdio MCP gets only this block + a safe baseline
      FAL_KEY: "<fal-key>"
      BLOTATO_API_KEY: "<blotato-key>"
      BLOTATO_TARGETS: '<json-array>'
      TOR_PROXY: "socks5://127.0.0.1:9050"
    tools:
      include: [get_transcript, identify_moments, cut_clips, analyze_clips, publish_clips, cleanup_files]
```

- **Env caveat (critical):** Hermes passes the stdio MCP subprocess **only** the `env:`
  block above plus a safe baseline — **not** the gateway's environment. So `config.py`'s
  `os.getenv("FAL_KEY")` etc. return `None` unless the keys are in this `env:` block. Do
  **not** rely on a shell `export` or a `.env` next to the code.
- Reload after editing config with `/reload-mcp` in a Hermes session, or
  `sudo systemctl restart hermes-gateway`.
- Manual tool test (same env the MCP server gets):
  `python scripts/call_tool.py get_transcript '{"video_url":"…"}'`.
- Verify Hermes sees the tools: `hermes tools` should list all six under
  `mcp-autoclipping` (note: `hermes tools` needs an interactive terminal).

## 7. External services

- **fal** (`fal-client`, `FAL_KEY`): NVIDIA Nemotron 3 Nano Omni for clip analysis —
  text `nvidia/nemotron-3-nano-omni` (`{prompt}` → `{output}`); video
  `nvidia/nemotron-3-nano-omni/video` (`{prompt, video_url}` → `{output}`). **Video
  input limit: mp4, ≤1080p, ≤2 min** — hence the 2-min window cap. fal is also the
  **vision** provider (§8). The fal account holds the paid credits.
- **Blotato** (`requests`, header `blotato-api-key`): presigned upload
  `POST https://backend.blotato.com/v2/media/uploads` (→ `presignedUrl` + `publicUrl`,
  then PUT bytes); publish `POST …/v2/posts`. ⚠️ `/v2/posts` is **per-account** — set
  `BLOTATO_TARGETS` (JSON array) to your connected accounts.
- **LLM (text model):** Owl Alpha via Hermes over **OpenRouter** (`openrouter/owl-alpha`)
  — **no Anthropic key**. Configured with `hermes model`. The OpenRouter account is
  free-tier (no credits), so paid models are **not** available there (→ vision uses fal).
- **Telegram:** bot token + allowed users are configured inside Hermes
  (`hermes gateway setup` → `~/.hermes/.env`), **not** as env vars elsewhere. A
  **self-hosted Telegram Bot API server** runs `--local` (20 MB → 2 GB uploads) and
  writes files to `/var/lib/telegram-bot-api/`. Hermes' telegram config points
  `base_url`/`base_file_url` at `http://127.0.0.1:8081` with `local_mode: true`, so it
  reads uploads from disk. **Two one-time requirements** for the local server to work:
  (a) the bot must be **logged out of the public Telegram API** first
  (`curl "https://api.telegram.org/bot<TOKEN>/logOut"` → `{"ok":true}`); (b) the bot-api
  server and Hermes run as the **same user** so Hermes can read the uploaded files.
- **Proxy** (`TOR_PROXY`, optional `YT_PROXY`): scoped to **transcript fetching only**
  (youtube-transcript-api + yt-dlp audio). The clipper does **not** use the proxy —
  video downloads go direct, to avoid throttling the proxy on large downloads.

## 8. Vision (image understanding)

Hermes' image vision (`auxiliary.vision` in `config.yaml`) runs on **fal**, because the
OpenRouter account has no credits for paid vision models. fal exposes an
**OpenAI-compatible** endpoint (`https://fal.run/openrouter/router/openai/v1`) serving
real VLMs (`openai/gpt-4o-mini`, `openai/gpt-4o`, `google/gemini-2.5-flash`).

The one wrinkle: fal requires `Authorization: Key <FAL_KEY>`, but Hermes' OpenAI client
sends `Bearer`, and the main model still needs `Bearer` — so a global header override
won't do. `deploy/fal-vision-proxy.py` (systemd `fal-vision-proxy.service`, loopback
`127.0.0.1:8089`) is a tiny stateless proxy that swaps `Bearer `→`Key ` and forwards to
fal. Config:

```yaml
auxiliary:
  vision:
    provider: openai
    model: openai/gpt-4o-mini
    base_url: 'http://127.0.0.1:8089/openrouter/router/openai/v1'
    api_key: '<FAL_KEY>'
```

Swap `model` to `openai/gpt-4o` or `google/gemini-2.5-flash` for stronger vision. Billed
on fal credits (gpt-4o-mini is fractions of a cent per image).

## 9. Local development (off the VPS)

```bash
python3 -m venv .venv && . .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
# Provide the same env the MCP server gets (FAL_KEY, BLOTATO_API_KEY, …) in your shell.
python scripts/call_tool.py get_transcript '{"video_url":"https://youtu.be/…"}'
```

`scripts/call_tool.py <tool_name> '<json-args>'` calls any of the six tools directly, the
same way Hermes' MCP server would — a faithful smoke test.

## 10. Hermes one-time setup (on the VPS, last step of a deploy)

After `deploy/install.sh`, configure Hermes once (persists under `~/.hermes`), then
enable the services. All on the VPS (SSH in first):

```bash
# 1. Pick the text model (interactive). Select Owl Alpha (openrouter/owl-alpha).
hermes model

# 2. Telegram gateway (interactive): paste the bot token + your numeric user id.
#    Writes them to ~/.hermes/.env.
hermes gateway setup

# 3. One-time: log the bot out of the public Telegram API so the local server can take
#    over (without this the local server rejects the bot).
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/logOut"

# 4. Hand-edit ~/.hermes/config.yaml: the telegram bot-api block (base_url/base_file_url
#    → http://127.0.0.1:8081, local_mode: true), the mcp_servers block (§6, with the
#    env: keys), and the auxiliary.vision block (§8).

# 5. Enable + start everything:
sudo systemctl enable --now tor telegram-bot-api fal-vision-proxy hermes-gateway
```

Verify: `systemctl is-active hermes-gateway` is `active`; the gateway log
(`~/.hermes/logs/gateway.log`) shows `Connected to Telegram (polling mode)` and
`local_mode`; send the bot a video to confirm the upload lands in
`/var/lib/telegram-bot-api/` and is read.

## 11. Open items

- **Built / working:** MCP-only tooling (six tools); bare-metal systemd deployment;
  self-hosted 2 GB Telegram uploads with the local-server `logOut` + same-user fix;
  image vision via the fal proxy; 10 windows + 2-min cap + sentence-boundary reasoning
  (§4a); clipper cuts local uploads with a 2s lead buffer (no URL download); per-target
  Blotato publishing; proxy scoped to transcript fetching.
- **Not built (future build prompts):** the HyperFrames editing/captioning stage (§4c).
- **Operational:** keep the deploy remote distinct from the other branch's remote; fill
  `BLOTATO_TARGETS`; confirm TikTok's `privacyLevel` enum against Blotato's docs.
- Open product question: the pipeline cuts the *window* clips; to publish only the
  30–60s "best moment", Hermes must re-cut (call `cut_clips` again with those
  timestamps) before `publish_clips`.
