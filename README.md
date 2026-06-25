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

## Continuing development on another machine (VS Code)

The git remote **is** this Hugging Face Space — it's the source of truth. Don't zip
the folder and don't push to GitHub; just clone the Space into a fresh VS Code
project.

1. In VS Code: `Ctrl+Shift+P` → **Git: Clone** → paste
   `https://huggingface.co/spaces/devproxa/Autoclipping` → **Open**.
   *(Or in a terminal: `git clone https://huggingface.co/spaces/devproxa/Autoclipping && code Autoclipping`.)*
2. When prompted, sign in with username `devproxa` and your HF **write** access
   token as the password.
3. Recreate `.env` (it's gitignored, so not in the clone) — see keys below.
4. Edit → `git commit` → `git push origin main` redeploys the Space automatically.

Full technical reference (architecture, build, tools, services) is in **`CLAUDE.md`**.

## Local development

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860
```

Copy the placeholder keys in `.env` and fill them in locally. In production these
are provided as **Space secrets**: `ANTHROPIC_API_KEY`, `FAL_KEY`,
`BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
