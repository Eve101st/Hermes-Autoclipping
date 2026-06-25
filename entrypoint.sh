#!/usr/bin/env bash
# ============================================================================
# Container entrypoint.
#
# Why this exists (instead of installing Hermes in the Dockerfile):
#   - The Hermes installer puts its CODE, its managed Node, and its managed uv
#     all under $HERMES_HOME (non-root layout). We want those on the PERSISTENT
#     bucket (/data) so they survive Space rebuilds.
#   - /data is a runtime-only mount: it does NOT exist during the Docker build.
#   So Hermes is installed at startup into /data/.hermes, idempotently. First
#   boot clones; later boots detect the existing checkout and just relink/update.
#
# The install runs in the BACKGROUND so the web app (and the HF health check)
# come up immediately; `hermes` appears on PATH a short while after boot.
# ============================================================================
set -euo pipefail

export HERMES_HOME=/data/.hermes
mkdir -p "$HERMES_HOME"

ensure_hermes() {
    if command -v hermes >/dev/null 2>&1; then
        echo "[entrypoint] hermes already on PATH — skipping install"
        return 0
    fi
    echo "[entrypoint] installing/restoring Hermes into $HERMES_HOME ..."
    if curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
        | bash -s -- --skip-setup --skip-browser --non-interactive; then
        echo "[entrypoint] Hermes ready (hermes -> $(command -v hermes 2>/dev/null || echo '?'))"
    else
        echo "[entrypoint] WARNING: Hermes install failed; app still serving. See logs above."
    fi
}

# Restore/instal Hermes without blocking the web server from binding the port.
ensure_hermes &

exec uvicorn app:app --host 0.0.0.0 --port 7860
