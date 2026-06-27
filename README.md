# Autoclipping

A Docker-based automation pipeline orchestrated by
[Hermes Agent](https://hermes-agent.nousresearch.com). You drive it from Telegram —
send a video link and it turns a long VOD into short vertical clips and publishes them.

The pipeline: fetch a video transcript → pick clip-worthy moments → cut vertical
clips → analyze each clip → publish to socials. A FastAPI app (`app.py`) serves a
health check and a `POST /tools/{name}` bridge for direct tool testing.

> This is the **`vps`** branch — a self-hosted deployment on any Docker host (Docker
> Compose + Caddy). A separate branch targets a managed Spaces host; the two diverge
> on hosting only and share the pipeline code.

## Architecture (short version)

| Piece | Role |
|-------|------|
| **Hermes Agent** | The orchestrator (text model: Owl Alpha) — decides what to do and calls the tools. |
| **Pipeline tools** | `get_transcript`, `identify_moments`, `cut_clips`, `analyze_clips`, `publish_clips` — registered to Hermes over MCP (`mcp_server.py`). |
| **FastAPI app** | Health check + `POST /tools/{name}` bridge for direct `curl` testing. |
| **Telegram gateway** | Your remote control (built into Hermes). |
| **Caddy** | Reverse proxy + automatic HTTPS in front of the app. |
| **`hermes-data` volume** | Persistent Hermes config/state — survives rebuilds. |

Deep technical reference (build, services, pipeline behaviour spec): **`AGENTS.md`**.

## Deploy

Prerequisites on the host: Docker + Docker Compose. For HTTPS on a domain, point a
DNS A record at the host IP and open inbound ports 80/443 in the firewall. (No domain
yet? See the note under *TLS* below.)

```bash
git clone <your-repo-url> autoclipping && cd autoclipping
git checkout vps

cp .env.example .env        # fill FAL_KEY, BLOTATO_API_KEY, BLOTATO_TARGETS
# edit Caddyfile            # set your domain + email (for automatic TLS)

docker compose up -d --build
```

**One-time Hermes setup** (persists in the `hermes-data` volume — done once):

```bash
docker compose exec app hermes model            # pick the text model (Owl Alpha)
docker compose exec app hermes gateway setup     # Telegram bot token + your numeric user id
# register the MCP server in /data/.hermes/config.yaml (see AGENTS.md §6 / §10)
docker compose restart app                        # loads keys + starts the Telegram gateway
```

**Verify:**

```bash
docker compose ps                                 # both services Up
docker compose exec app hermes tools              # lists the five pipeline tools
curl -s http://<host>/                            # {"status":"...live","hermes":"installed"}
```

`BLOTATO_TARGETS` is a JSON array, one entry per connected social account (Blotato's
publish API is per-account). Each entry needs `accountId`, `platform`, and a `target`;
some platforms require extra fields (e.g. TikTok privacy flags, a YouTube `content`
block). See `.env.example` and `AGENTS.md` §7 for the per-platform shape.

**TLS / no domain yet:** Caddy's default config gets a Let's-Encrypt cert for your
domain. With only an IP, set the `Caddyfile` to serve plain HTTP instead:

```
:80 {
	reverse_proxy app:7860
}
```

(Telegram traffic is outbound, so inbound TLS isn't required to operate; add the
domain + cert later by restoring the domain `Caddyfile`.)

## Use it

In Telegram, message your bot a video link, e.g.:

```
Clip this: <YouTube or Twitch URL>
```

Hermes runs the pipeline, then (by default) pauses to show you the candidate clips
with virality scores and captions and waits for your approval before publishing.

## Update

```bash
git pull && docker compose up -d --build      # rebuilds app/tool code
```

Hermes itself lives in the persistent volume, so a rebuild does **not** replace it.
To upgrade Hermes, update it from inside the container or recreate the `hermes-data`
volume (which then re-runs the one-time setup above).

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env         # fill in keys
uvicorn app:app --host 0.0.0.0 --port 7860
```

Test a tool directly:

```bash
curl -X POST localhost:7860/tools/get_transcript \
  -H 'Content-Type: application/json' -d '{"video_url":"https://youtu.be/..."}'
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Health shows `"hermes":"installing"` | `hermes` not on PATH in the container | `docker compose exec app which hermes`; check the build's Hermes install step in `docker compose logs app`. |
| `hermes tools` is empty | MCP not registered/reloaded, or `mcp_server.py` errored | confirm the `mcp_servers` block in `/data/.hermes/config.yaml`; `docker compose restart app`; check `docker compose exec app python -c "import mcp_server"`. |
| Telegram bot silent | Gateway not started/configured, or your user id isn't allow-listed | confirm `hermes gateway setup` was done; `docker compose restart app`; check `docker compose logs app` for the gateway launch. |
| HTTPS / cert errors | DNS not pointed, or 80/443 closed | confirm the A record resolves and ports 80/443 are open; check `docker compose logs caddy`. |
| Lost Hermes config after a change | The `hermes-data` volume was removed | re-run the one-time setup. Avoid `docker compose down -v` (`-v` deletes named volumes). |
