# Autoclipping

An automation pipeline orchestrated by
[Hermes Agent](https://hermes-agent.nousresearch.com). You drive it from Telegram — send
a video link (or upload a video) and it turns a long VOD into short vertical clips and
publishes them.

The pipeline: fetch a transcript → pick clip-worthy moments → cut vertical clips →
analyze each clip → (edit — coming) → publish to socials.

> This is the **`vps`** branch — a **bare-metal** deployment: native `systemd` services
> on one Ubuntu 22.04 VPS, no Docker. A separate branch targets a different managed host
> and shares only the pipeline code.

## Architecture (short version)

| Piece | Role |
|-------|------|
| **Hermes Agent** | The orchestrator (text model: Owl Alpha via OpenRouter) — decides what to do and calls the tools. Runs as `hermes-gateway.service`. |
| **Pipeline tools** | `get_transcript`, `identify_moments`, `cut_clips`, `analyze_clips`, `publish_clips`, `cleanup_files` — registered to Hermes over MCP (`mcp_server.py`). |
| **Telegram gateway** | Your remote control (built into Hermes, outbound long-poll — no inbound port). |
| **Self-hosted Bot API** | `telegram-bot-api.service`, `--local` — raises uploads 20 MB → 2 GB and writes files to disk. |
| **fal vision proxy** | `fal-vision-proxy.service` — lets Hermes' image vision run on fal (`gpt-4o-mini`). |
| **Tor** | Loopback SOCKS5 proxy, scoped to transcript fetching. |

Deep technical reference (build, services, pipeline behaviour spec): **`AGENTS.md`**.

## Deploy

You need: an **Ubuntu 22.04 VPS** with a sudo-capable login, and your accounts'
keys (fal, Blotato, a Telegram bot token, Telegram `api_id`/`api_hash`). Our reference
box runs the **Ubuntu 22.04** base image; no other provider assumptions. Everything is
outbound, so **no domain, TLS, or open inbound ports are required.**

SSH into the VPS, then:

```bash
# 1. Clone the repo to /opt and build everything (deps, venv, Tor, the Bot API server
#    built from source, the systemd units). Idempotent; safe to re-run.
sudo mkdir -p /opt/autoclipping && sudo chown "$USER:$USER" /opt/autoclipping
git clone <your-repo-url> /opt/autoclipping
cd /opt/autoclipping && git checkout vps
cp .env.example .env        # fill TELEGRAM_API_ID / TELEGRAM_API_HASH
sudo bash deploy/install.sh
```

```bash
# 2. Install Hermes Agent natively (its own installer).
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive
```

**One-time Hermes setup** (persists under `~/.hermes`):

```bash
hermes model            # pick the text model (Owl Alpha)
hermes gateway setup     # Telegram bot token + your numeric user id

# Log the bot out of the public Telegram API so the local server can take over:
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/logOut"

# Edit ~/.hermes/config.yaml: the telegram bot-api block (base_url → 127.0.0.1:8081,
# local_mode: true), the mcp_servers block, and the auxiliary.vision block.
# (See AGENTS.md §6, §7, §8 for the exact blocks.)

# Start everything (and enable on boot):
sudo systemctl enable --now tor telegram-bot-api fal-vision-proxy hermes-gateway
```

**Verify:**

```bash
systemctl is-active tor telegram-bot-api fal-vision-proxy hermes-gateway   # all "active"
tail -n 20 ~/.hermes/logs/gateway.log     # "Connected to Telegram (polling mode)" + "local_mode"
```

`BLOTATO_TARGETS` is a JSON array, one entry per connected social account (Blotato's
publish API is per-account). Each entry needs `accountId`, `platform`, and a `target`;
some platforms need extra fields (TikTok privacy flags, a YouTube `content` block). See
`AGENTS.md` §7. The pipeline secrets (`FAL_KEY`, `BLOTATO_API_KEY`, `BLOTATO_TARGETS`)
go in the **`mcp_servers` `env:` block** of `~/.hermes/config.yaml`, not in a shell
env — Hermes only passes that block to the tools (`AGENTS.md` §6).

## Use it

In Telegram, send your bot a video link **or upload a video file**, e.g.:

```
Clip this: <YouTube or Twitch URL>
```

Hermes runs the pipeline, then (by default) pauses to show you the candidate clips with
virality scores and captions and waits for your approval before publishing. Send
`/cleanup` to free disk from previous sessions.

## Update

```bash
cd /opt/autoclipping && git pull
sudo systemctl restart hermes-gateway     # reloads tool/config changes
```

Hermes itself lives under `~/.hermes` and is independent of the repo. Rebuild the
`telegram-bot-api` binary only if its upstream source changed.

## Local development (off the VPS)

```bash
python3 -m venv .venv && . .venv/bin/activate     # .venv\Scripts\activate on Windows
pip install -r requirements.txt
# Provide FAL_KEY / BLOTATO_API_KEY / … in your shell, then:
python scripts/call_tool.py get_transcript '{"video_url":"https://youtu.be/…"}'
```

`scripts/call_tool.py <tool> '<json-args>'` calls any of the six tools directly — the
same way Hermes' MCP server would.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Bot silent | Gateway not running/configured, or your user id isn't allow-listed | `systemctl is-active hermes-gateway`; confirm `hermes gateway setup` was done; `journalctl -u hermes-gateway -n 50`. |
| `hermes tools` empty | MCP not registered/reloaded, or `mcp_server.py` errored | confirm the `mcp_servers` block in `~/.hermes/config.yaml`; `sudo systemctl restart hermes-gateway`; `/opt/autoclipping/.venv/bin/python -c "import mcp_server"`. |
| Uploaded file "not found" | Bot not logged out of the public API, or a user-permission mismatch | run the `logOut` curl above; ensure `telegram-bot-api` and `hermes-gateway` run as the **same** user (so uploads are readable). |
| Vision says "unavailable / 404" | `fal-vision-proxy` down, or `auxiliary.vision` misconfigured | `systemctl is-active fal-vision-proxy`; confirm the `auxiliary.vision` block points at `127.0.0.1:8089` with the fal key (`AGENTS.md` §8). |
| Transcript fails on YouTube | proxy/IP throttling | confirm `tor` is active (`127.0.0.1:9050`), or set `YT_PROXY`. |
