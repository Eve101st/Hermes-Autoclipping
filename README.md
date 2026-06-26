# Autoclipping (VPS)

Docker-based automation pipeline orchestrated by
[Hermes Agent](https://hermes-agent.nousresearch.com). This is the **VPS branch**
(`vps`), deployed to a Tencent VPS via Docker Compose. The `main` branch is the
Hugging Face Spaces build — see that branch for the HF setup.

> Why two branches: Hugging Face Spaces and Telegram can't reach each other at the
> network level, so the Hermes Telegram gateway can't run on HF. The VPS gives it
> real network access.

The pipeline: fetch a video transcript → pick clip-worthy moments → cut vertical
clips → analyze each clip → publish to socials. A FastAPI app (`app.py`) serves a
health check and a `POST /tools/{name}` bridge for direct tool testing.

## Deploy (Tencent VPS)

Prerequisites on the VPS: Docker + Docker Compose, a domain with a DNS A record
pointing at the VPS IP, and ports 80/443 open in the Tencent security group.

```bash
git clone <your-github-repo> autoclipping && cd autoclipping
git checkout vps

cp .env.example .env        # fill FAL_KEY, BLOTATO_API_KEY, BLOTATO_TARGETS
# edit Caddyfile            # set your domain + email

docker compose up -d --build
```

One-time Hermes setup (persists in the `hermes-data` volume):

```bash
docker compose exec app hermes model           # pick Owl Alpha
docker compose exec app hermes gateway setup    # Telegram bot token + your user id
# register the MCP server in /data/.hermes/config.yaml (see AGENTS.md §6)
docker compose restart app
```

Health check (through the proxy): `https://<your-domain>/` returns
`{"status":"Autoclipping pipeline is live","hermes":"installed"}`.

Update app/tool code later: `git pull && docker compose up -d --build`.

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env         # fill in keys
uvicorn app:app --host 0.0.0.0 --port 7860
```

Full technical reference (architecture, build, tools, services) is in **`AGENTS.md`**
(the single source of truth; agents should read it first). Step-by-step deploy
runbook: **`STARTUP_GUIDE.md`**.
