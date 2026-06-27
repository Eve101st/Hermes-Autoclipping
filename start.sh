#!/usr/bin/env bash
# ============================================================================
# Container entrypoint (VPS build).
#
# On the VPS, Hermes is BAKED INTO THE IMAGE at build time (see Dockerfile) and
# seeded into the `/data` named volume on first run, so there is:
#   - NO runtime install, and
#   - NONE of the Hugging Face /data FUSE workarounds (exec-bit / venv-symlink
#     repairs) — a real filesystem preserves them.
#
# So this script just:
#   1. Launch the Hermes Telegram gateway IF it's configured (background).
#   2. Serve the tool endpoints + health check with uvicorn (foreground).
#
# Hermes calls the pipeline tools through the MCP server (mcp_server.py), which
# Hermes spawns itself once it's registered in /data/.hermes/config.yaml. The
# uvicorn `POST /tools/{name}` bridge stays available for manual curl testing.
#
# uvicorn is the FOREGROUND process so the container stays up (and reachable)
# even before Hermes/Telegram are configured.
# ============================================================================
set -uo pipefail

export HERMES_HOME=/data/.hermes
# Put the venv's bin straight on PATH so `hermes` resolves from the persistent
# /data volume.
export PATH="$HERMES_HOME/hermes-agent/venv/bin:$PATH"

start_gateway() {
    if ! command -v hermes >/dev/null 2>&1; then
        echo "[start] Telegram gateway not started: hermes not on PATH."
        return 0
    fi
    # The Telegram token lives in Hermes' own config (set by `hermes gateway setup`),
    # not as a container env var. Only launch the gateway once it's been configured.
    if ! grep -qs 'TELEGRAM_BOT_TOKEN' "$HERMES_HOME/.env" "$HERMES_HOME/config.yaml"; then
        echo "[start] Telegram gateway not started: not configured in $HERMES_HOME."
        echo "[start]   -> run 'hermes gateway setup' inside the container, then restart."
        return 0
    fi
    # `hermes gateway` reads the bot token + allowlists from the process
    # environment, not from $HERMES_HOME/.env directly. `hermes gateway setup`
    # writes them to that file, so load them into the env before launching, or
    # the gateway comes up with "no messaging platforms enabled".
    set -a
    . "$HERMES_HOME/.env"
    set +a
    echo "[start] launching Hermes Telegram gateway (hermes gateway) ..."
    hermes gateway \
        || echo "[start] Hermes gateway exited — is the model (Owl Alpha) configured? ('hermes model')"
}

# Bring up the gateway in the background so it never blocks uvicorn's port bind.
start_gateway &

exec uvicorn app:app --host 0.0.0.0 --port 7860
