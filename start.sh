#!/usr/bin/env bash
# ============================================================================
# Container entrypoint (Phase 3). Supersedes the earlier entrypoint.sh.
#
#   1. Restore Hermes into the persistent bucket /data/.hermes (idempotent,
#      background) — see CLAUDE.md §5 for why this is done at runtime, not build.
#   2. Launch the Hermes Telegram gateway IF it's configured (background).
#   3. Serve the tool endpoints + health check with uvicorn (foreground).
#
# Hermes calls the pipeline tools through the MCP server (mcp_server.py), which
# Hermes spawns itself once it's registered in /data/.hermes/config.yaml. The
# uvicorn `POST /tools/{name}` bridge stays available for manual curl testing.
#
# uvicorn is the FOREGROUND process so the Space stays "Running" (and the dev
# terminal stays reachable) even before Hermes/Telegram are configured.
# ============================================================================
set -uo pipefail

export HERMES_HOME=/data/.hermes
mkdir -p "$HERMES_HOME"

ensure_hermes() {
    if command -v hermes >/dev/null 2>&1; then
        echo "[start] hermes already on PATH."
        return 0
    fi
    echo "[start] installing/restoring Hermes into $HERMES_HOME ..."
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
        | bash -s -- --skip-setup --skip-browser --non-interactive \
        || echo "[start] WARNING: Hermes install failed (see logs above)."
}

start_gateway() {
    if ! command -v hermes >/dev/null 2>&1; then
        echo "[start] Telegram gateway not started: hermes not installed."
        return 0
    fi
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        echo "[start] Telegram gateway not started: TELEGRAM_BOT_TOKEN unset."
        echo "[start]   -> configure it with 'hermes gateway setup' in the dev terminal, then restart."
        return 0
    fi
    echo "[start] launching Hermes Telegram gateway (hermes gateway) ..."
    hermes gateway \
        || echo "[start] Hermes gateway exited — is the model provider configured? ('hermes model')"
}

# Restore Hermes then bring up the gateway, without blocking uvicorn's port bind.
( ensure_hermes; start_gateway ) &

exec uvicorn app:app --host 0.0.0.0 --port 7860
