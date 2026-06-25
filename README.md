---
title: Autoclipping
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Autoclipping

Docker-based automation pipeline running on Hugging Face Spaces, orchestrated by
[Hermes Agent](https://hermes-agent.nousresearch.com).

## Status

Phase 1 — infrastructure scaffold. The root endpoint returns a health check:

```json
{ "status": "Autoclipping pipeline is live", "hermes": "installed" }
```

## Local development

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860
```

Copy the placeholder keys in `.env` and fill them in locally. In production these
are provided as **Space secrets**: `ANTHROPIC_API_KEY`, `FAL_KEY`,
`BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
