# Autoclipping — Build From Scratch (4 Phases)

This is the complete build process for Autoclipping: a Telegram bot that turns long
videos into short vertical clips and posts them, orchestrated by **Hermes Agent**. It is
written so a **non-technical person** can build it by handing each phase to an AI coding
agent (Claude Code, Cursor, etc.) and running a few copy-paste commands.

**Architecture:** everything runs **bare-metal** on one **Ubuntu 22.04** server as native
`systemd` services — there is **no Docker** anywhere. (Our reference box uses the
"Ubuntu 22.04-Docker26" base image; we simply don't use its Docker.) Everything is
outbound, so **no domain, no TLS, no open inbound ports** are required.

---

## What you need before you start (gather these once)

You don't need to understand any of this — just have it ready:

1. **A server (VPS)** running **Ubuntu 22.04**, and the **SSH private key** file it gave
   you (a `.pem` file). Note the server's **IP address** and the **login username**
   (commonly `ubuntu`). *Don't share the key or IP with anyone.*
2. **A private Git repository** (e.g. a private GitHub repo) — empty is fine. Have its
   URL ready. Keep it **private**.
3. **Accounts + keys** (paste them only when a step asks):
   - **fal** account → a `FAL_KEY` (https://fal.ai). This pays for clip analysis + vision.
   - **Blotato** account → a `BLOTATO_API_KEY` + your connected social accounts (https://blotato.com).
   - **A Telegram bot** → message **@BotFather** in Telegram, `/newbot`, and copy the
     **bot token**. Also get your own **numeric Telegram user id** (message **@userinfobot**).
   - **Telegram API id + hash** → https://my.telegram.org/apps (these let the bot accept
     big uploads). The `api_hash` is a secret.
4. **A Windows PC** with the OpenSSH client (built into Windows 10/11) to run the SSH
   steps. (Mac/Linux work too; the SSH commands are the same minus the Windows
   permission fix.)

> **Golden rule:** never paste your keys, bot token, server IP, or `.pem` contents into a
> public chat or commit them to the repo. The build keeps them out of the code on
> purpose.

## How to use the 4 phases

- **Phase 1 & 2** are **AI build prompts** — copy the whole prompt block into your AI
  coding agent and let it build + push the project. You don't write code.
- **Phase 3 & 4** are **you, on the server** — copy-paste the exact commands shown. The
  only manual work in the entire build is SSH-ing in and running these.
- Do them **in order**. By the end of Phase 4 you run Hermes' own setup screen and the
  bot is live.

Throughout, replace the **`<PLACEHOLDERS>`** with your own values:
`<REPO_URL>`, `<SERVER_IP>`, `<SSH_USER>` (usually `ubuntu`), `<KEY.pem>` (path to your
key file), `<BOT_TOKEN>`, `<FAL_KEY>`, `<BLOTATO_API_KEY>`, `<TELEGRAM_API_ID>`,
`<TELEGRAM_API_HASH>`, `<YOUR_TELEGRAM_USER_ID>`.

---

# PHASE 1 — Build the clipping pipeline (AI build prompt)

> Copy everything in this block to your AI coding agent.

```
Build a Python project called "autoclipping" — the tool layer for a Telegram clip bot
orchestrated by Hermes Agent. NO web framework, NO Docker — just plain Python modules
exposed to Hermes over MCP. Create exactly these files:

requirements.txt:
  youtube-transcript-api, yt-dlp, faster-whisper, httpx, python-dotenv, fal-client,
  requests, fastmcp   (one per line, no versions)

config.py:
  Loads env vars and exposes FAL_KEY and BLOTATO_API_KEY as importable constants (via
  os.getenv, with python-dotenv load_dotenv() for local dev). Comment that on the server
  these come from the Hermes mcp_servers env: block, not a .env file.

tools/_timecode.py:
  to_seconds(value) -> float. Accepts seconds (int/float) or "HH:MM:SS" / "MM:SS"
  strings. Used by the clipper.

tools/transcript.py:
  get_transcript(video_url) -> str. video_url is a YouTube/Twitch URL OR a local file
  path. YouTube -> youtube-transcript-api (with an optional residential proxy from
  YT_PROXY, falling back to TOR_PROXY). Twitch -> yt-dlp subtitles. Local file or
  fallback -> faster-whisper (CPU) on yt-dlp-extracted audio. Return one line per
  segment, each prefixed "[HH:MM:SS] text". Import yt-dlp and faster-whisper lazily so
  importing the module never fails at boot.

tools/analyzer.py:
  identify_moments(transcript) -> list[dict]: call the fal text model
  "nvidia/nemotron-3-nano-omni" to return EXACTLY 10 candidate clip windows, each
  {start, end, reason}, each <= 2 minutes, placed on SENTENCE BOUNDARIES (never
  mid-sentence — confirm the boundary in each 'reason'). Cap at 10.
  analyze_clips(clip_paths) -> list[dict]: for each clip, call the fal video model
  "nvidia/nemotron-3-nano-omni/video" (upload via fal_client) to return {start, end,
  caption, virality_score} — the single best 30-60s moment, a scroll-stopping caption
  with hashtags, and a 0-100 score. Read FAL_KEY from the env (os.environ first, then
  config.FAL_KEY); raise a clear error if missing.

tools/clipper.py:
  cut_clips(video_path, timestamps) -> list[str]. video_path is a LOCAL video file (a
  Telegram upload) — there is NO URL download (downloading source video is unviable on a
  server IP). If video_path isn't a local file, raise a clear error. For each timestamp
  {start,end}, ffmpeg-cut the window to a 9:16 mp4 in /tmp/clips, center-cropped to
  1080x1920, starting LEAD_BUFFER_SECONDS=2 early (clamped at 0) so a clip never opens
  mid-sentence. Audio+video stay together. Return the output paths.

tools/reframe.py:
  The smart vertical-reframe compositor (so gameplay clips aren't butchered by a blind
  center-crop). All renders output 1080x1920 mp4. Regions are {x,y,w,h} in source
  pixels. Functions:
    capture_frame(video_path, at_seconds=0.0) -> str: ffmpeg grabs ONE frame to a PNG
      (for the vision probe + QA).
    qa_frames(clip_path) -> dict: capture the first and last frame of a finished clip ->
      {first, last, duration} (ffprobe for duration).
    reframe_vertical(src, out_path, layout=None, start=None, duration=None) -> str:
      cut [start, start+duration] if given, then render 1080x1920 via an ffmpeg
      -filter_complex producing [out], per layout {"mode": ...}:
        center   - scale-to-cover + center-crop.
        fit_blur - whole frame fit to width over a blurred copy (nothing lost).
        crop     - crop region {x,y,w,h} then cover to 9:16.
        split    - stack two regions (top/bottom {x,y,w,h}, optional top_h=1280) e.g.
                   gameplay over facecam.
        overlay  - base region fills 9:16, cam region overlaid as picture-in-picture
                   (base/cam {x,y,w,h}, optional pip_w=410, pos_x/pos_y).
      Keep both gameplay and facecam as MOVING video. Use libx264/veryfast + aac +
      faststart. Map "0:a?" so audio is optional.

tools/publisher.py:
  publish_clips(clip_paths, captions) -> list[dict]. For each clip: Blotato presigned
  upload (POST https://backend.blotato.com/v2/media/uploads -> presignedUrl + publicUrl,
  then PUT the bytes), then POST .../v2/posts ONCE PER configured target. Read targets
  from BLOTATO_TARGETS (JSON array; each entry accountId+platform+target, some with a
  content block). Header "blotato-api-key": BLOTATO_API_KEY. Return one result per
  clip/target.

tools/cleanup.py:
  cleanup_files() -> dict. Delete /tmp/clips, /tmp/frames, the Hermes upload cache, and
  the local Telegram Bot API server's downloaded files. Return {files_deleted, freed_mb,
  locations}.

tools/__init__.py:
  A docstring listing each tool's signature.

mcp_server.py:
  A FastMCP stdio server that wraps ALL of these as MCP tools (so Hermes can call them):
  get_transcript, identify_moments, cut_clips, analyze_clips, publish_clips,
  cleanup_files, capture_frame, reframe_vertical, qa_frames. Each @mcp.tool delegates to
  the matching tools/ function and has a clear docstring. End with
  `if __name__ == "__main__": mcp.run()`.

scripts/call_tool.py:
  A tiny CLI: `python scripts/call_tool.py <tool_name> '<json-args>'` that imports the
  tool modules, dispatches to the named tool, and prints the JSON result. Lists all nine
  tools. (Manual test harness — no web server.)

Make every module import cleanly even when optional deps aren't installed (lazy imports).
Do not create a Dockerfile, docker-compose, app.py, FastAPI app, or any web server.
```

**When the AI finishes Phase 1:** you should have a folder with `tools/`, `mcp_server.py`,
`scripts/call_tool.py`, `requirements.txt`, `config.py`. (You won't run it yet.)

---

# PHASE 2 — Build the deployment kit + docs, and push to your repo (AI build prompt)

> Copy everything in this block to your AI coding agent (continue in the same project).

```
Now add the bare-metal deployment kit and docs for the autoclipping project. NO Docker
anywhere. Target: one Ubuntu 22.04 server, everything run as the login user via systemd.

deploy/install.sh — an idempotent bootstrap script (run with sudo on the server). It must:
  1. apt-get install: python3.10 + python3.10-venv + python3-pip, ffmpeg, git, ripgrep,
     curl, xz-utils, ca-certificates, tor; Node.js 22 (NodeSource) and uv (astral) for
     Hermes. (Use a PYTHON=python3.10 variable; Ubuntu 22.04 has no real 3.11.)
  2. Write /etc/tor/torrc with: SocksPort 127.0.0.1:9050 / SafeSocks 1 / TestSocks 1.
  3. Create the venv at /opt/autoclipping/.venv and pip install -r requirements.txt.
  4. Build the Telegram Bot API server FROM SOURCE (tdlib/telegram-bot-api) to a native
     binary at /usr/local/bin/telegram-bot-api. The compile is RAM-hungry: add a 4G
     swapfile first if none exists, and build with `nice -19` and `-j2`. (cmake + g++ +
     zlib1g-dev + libssl-dev + gperf + make are build deps.)
  5. Create /var/lib/telegram-bot-api owned by the run user (mode 0750).
  6. Install the three systemd unit files below to /etc/systemd/system and daemon-reload.
  It must NOT start/enable any service and must NOT run Hermes — those are the final
  manual step. Print a short "next steps" banner at the end.

deploy/systemd/telegram-bot-api.service — runs /usr/local/bin/telegram-bot-api with
  --local --http-port=8081 --dir=/var/lib/telegram-bot-api, User=ubuntu,
  EnvironmentFile=/opt/autoclipping/.env (TELEGRAM_API_ID / TELEGRAM_API_HASH),
  Restart=on-failure. Comment that --local writes uploads to disk (20MB -> 2GB).

deploy/systemd/hermes-gateway.service — runs the installed hermes binary `hermes gateway`,
  User=ubuntu, WorkingDirectory=/opt/autoclipping,
  EnvironmentFile=/home/ubuntu/.hermes/.env, TimeoutStopSec=240, Restart=on-failure.
  Comment: FAL_KEY/BLOTATO_* must NOT be here — they go in the Hermes mcp_servers env:
  block; this file only carries the gateway's Telegram token.

deploy/systemd/fal-vision-proxy.service — runs `python3 /opt/autoclipping/deploy/fal-vision-proxy.py`,
  User=ubuntu, Environment=FAL_PROXY_PORT=8089, Restart=on-failure.

deploy/fal-vision-proxy.py — a tiny stdlib HTTP reverse proxy on 127.0.0.1:8089 that
  forwards every request to fal.run, rewriting the Authorization header from
  "Bearer X" to "Key X" (fal needs "Key"; the OpenAI client Hermes uses sends "Bearer").
  Stateless, no extra deps. (This lets Hermes' image vision run on fal's
  OpenAI-compatible endpoint, billed on fal credits.)

.env.example — documents that on the server this file only holds TELEGRAM_API_ID /
  TELEGRAM_API_HASH (read by telegram-bot-api.service), while the pipeline secrets
  (FAL_KEY, BLOTATO_API_KEY, BLOTATO_TARGETS, TOR_PROXY) go in the Hermes mcp_servers
  env: block. NO Anthropic key; Telegram bot token is set via `hermes gateway setup`.

AGENTS.md and README.md — concise docs describing the bare-metal architecture (the four
  systemd services, the /opt/autoclipping + ~/.hermes layout), the nine MCP tools, the
  fal vision proxy, and the deploy + one-time Hermes setup. Keep them sanitized: no IPs,
  no names/emails, no secrets — refer host specifics to a gitignored INTERNAL.md.

.gitignore — ignore .env, INTERNAL.md, PROJECT_STATUS.md, SESSION_HANDOFF.md, .venv/,
  __pycache__/.

Then initialize git and push to my private repo:
  git init && git add -A && git commit -m "autoclipping: bare-metal build"
  git branch -M vps
  git remote add origin <REPO_URL>
  git push -u origin vps
```

**When the AI finishes Phase 2:** your private repo has the full project on the `vps`
branch. Now it's your turn on the server.

---

# PHASE 3 — Provision the server (you, over SSH)

You'll SSH into your Ubuntu 22.04 server and run two commands. **This is the only place
you touch the server directly.** It downloads everything and builds the upload server
from source (~20–40 min — that's normal).

### 3.1 Lock down your key file (Windows only — run in PowerShell)

Windows refuses to use an SSH key that other accounts can read. Fix its permissions
(replace `<KEY.pem>` with the full path to your key file, and `<YOU>` with your Windows
username, e.g. the output of `whoami`):

```powershell
icacls "<KEY.pem>" /inheritance:r
icacls "<KEY.pem>" /grant:r "<YOU>:R"
```

### 3.2 SSH into the server

```powershell
ssh -i "<KEY.pem>" -o IdentitiesOnly=yes <SSH_USER>@<SERVER_IP>
```

(Type `yes` if it asks about authenticity the first time.) You're now "on the server" —
the next commands run there.

### 3.3 Get the code and build everything

```bash
sudo mkdir -p /opt/autoclipping && sudo chown "$USER:$USER" /opt/autoclipping
git clone <REPO_URL> /opt/autoclipping
cd /opt/autoclipping && git checkout vps
cp .env.example .env
nano .env        # fill ONLY TELEGRAM_API_ID and TELEGRAM_API_HASH, then Ctrl-O, Enter, Ctrl-X

sudo bash deploy/install.sh        # installs deps + builds the upload server (~20-40 min)
```

```bash
# Install Hermes Agent itself (its own installer):
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive
```

**When Phase 3 finishes:** everything is installed but nothing is running yet (no bot
token, no config). Stay SSH-ed in for Phase 4.

---

# PHASE 4 — Configure Hermes and go live (you, over SSH — the last step)

Still on the server. You'll run Hermes' interactive setup, paste your keys when asked,
and start the bot. After this it's live.

### 4.1 Hermes interactive setup

```bash
hermes model
```
Pick the text model when the screen appears (we use **Owl Alpha / `openrouter/owl-alpha`**
— it's free and needs no extra key).

```bash
hermes gateway setup
```
Paste your **`<BOT_TOKEN>`** and your **`<YOUR_TELEGRAM_USER_ID>`** when prompted.

### 4.2 Let the local upload server take over the bot (one-time, required)

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/logOut"
```
You should see `{"ok":true}`. (Without this, the 2 GB upload server can't serve your bot.)

### 4.3 Add the pipeline config + secrets to Hermes

Open Hermes' config and add the two blocks below:

```bash
nano ~/.hermes/config.yaml
```

Find the **top-level `telegram:`** section and, under its `extra:`, set the local upload
server + turn on local mode:

```yaml
telegram:
  extra:
    base_url: "http://127.0.0.1:8081/bot"
    base_file_url: "http://127.0.0.1:8081/file/bot"
    local_mode: true
```

Find the **`auxiliary:`** section and set `vision:` to fal (through the proxy):

```yaml
auxiliary:
  vision:
    provider: openai
    model: openai/gpt-4o-mini
    base_url: "http://127.0.0.1:8089/openrouter/router/openai/v1"
    api_key: "<FAL_KEY>"
```

Add this **`mcp_servers:`** block at the top level (this is how Hermes reaches your tools,
and the ONLY place the pipeline secrets live):

```yaml
mcp_servers:
  autoclipping:
    command: /opt/autoclipping/.venv/bin/python
    args: ["/opt/autoclipping/mcp_server.py"]
    enabled: true
    env:
      FAL_KEY: "<FAL_KEY>"
      BLOTATO_API_KEY: "<BLOTATO_API_KEY>"
      BLOTATO_TARGETS: '<YOUR_BLOTATO_TARGETS_JSON>'
      TOR_PROXY: "socks5://127.0.0.1:9050"
    tools:
      include: [get_transcript, identify_moments, cut_clips, analyze_clips,
                publish_clips, cleanup_files, capture_frame, reframe_vertical, qa_frames]
```

Save (Ctrl-O, Enter, Ctrl-X).

> `<YOUR_BLOTATO_TARGETS_JSON>` is a JSON array, one entry per connected social account,
> e.g. `[{"accountId":"123","platform":"instagram","target":{"targetType":"instagram"}}]`.
> Get the account ids from your Blotato dashboard.

### 4.4 Start everything (and enable on boot)

```bash
sudo systemctl enable --now tor telegram-bot-api fal-vision-proxy hermes-gateway
```

### 4.5 Confirm it's alive

```bash
systemctl is-active tor telegram-bot-api fal-vision-proxy hermes-gateway   # four "active"
tail -n 20 ~/.hermes/logs/gateway.log                                      # "Connected to Telegram (polling mode)"
```

Now message your bot in Telegram and **upload a video file** with something like
"clip this". It will transcribe, pick moments, cut 9:16 vertical clips, reframe gameplay
so the facecam + action are both visible, score them, and pause for your approval before
posting. Send `/cleanup` anytime to free disk.

You're done — the bot is live, and the only thing you did by hand was SSH in twice.

---

## Appendix — how the bot decides the clip layout (the "perform well" part)

When clipping, the agent should: grab a frame at the clip's start (`capture_frame`) →
look at it with the vision model → decide the content type and where the facecam /
gameplay / point-of-interest are → call `reframe_vertical` with the right mode
(`split` or `overlay` for gameplay + facecam, `fit_blur` when nothing should be lost,
`center` for a centered talking head) → run `qa_frames` and re-do if the framing is off.
Hermes Agent learns this orchestration over a few runs. The deterministic ffmpeg
compositor is built; the judgement improves with use.
