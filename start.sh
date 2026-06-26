#!/usr/bin/env bash
# ============================================================================
# Container entrypoint (Phase 3). Supersedes the earlier entrypoint.sh.
#
#   1. Restore Hermes into the persistent bucket /data/.hermes (idempotent,
#      background) — see AGENTS.md §5 for why this is done at runtime, not build.
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

repair_venv() {
    # The venv's python interpreter symlinks have been observed missing at least
    # once, breaking the hermes shebang (#!.../venv/bin/python3 -> sh reports
    # "not found"). Root cause not yet confirmed: could be persistence-layer
    # symlink loss on /data, or a one-time deletion by a prior repair step. The
    # hermes-agent tree itself survives restarts intact, which argues against a
    # per-boot drop. Recreate the links idempotently against the image's base
    # Python on every boot; no-op when already healthy.
    local vbin="$HERMES_HOME/hermes-agent/venv/bin"
    local base="/usr/local/bin/python3.11"
    [ -x "$base" ] || base="$(command -v python3.11 || command -v python3)"
    [ -d "$vbin" ] && [ -n "$base" ] || return 0
    ln -sfn "$base"    "$vbin/python3.11"
    ln -sfn python3.11 "$vbin/python3"
    ln -sfn python3    "$vbin/python"
}

repair_perms() {
    # The HF persistent store (/data) is a FUSE mount that does NOT preserve the
    # execute bit when the installer writes Hermes' venv scripts, so `hermes` fails
    # with "cannot execute: Permission denied" even though /data is exec-capable.
    # Re-apply +x to Hermes' binaries on every boot (idempotent). See AGENTS.md §5.
    for d in "$HERMES_HOME/hermes-agent/venv/bin" "$HERMES_HOME/bin" "$HERMES_HOME/node/bin"; do
        [ -d "$d" ] && chmod -R u+x "$d" 2>/dev/null
    done
    if command -v hermes >/dev/null 2>&1 && hermes --version >/dev/null 2>&1; then
        echo "[start] hermes executable OK ($(hermes --version 2>/dev/null | head -1))"
    else
        echo "[start] WARNING: hermes still not runnable after perms repair."
    fi
}

start_gateway() {
    if ! command -v hermes >/dev/null 2>&1; then
        echo "[start] Telegram gateway not started: hermes not installed."
        return 0
    fi
    # The Telegram token lives in Hermes' own config (set by `hermes gateway setup`),
    # not as a Space secret / container env var. Only launch the gateway once it's
    # been configured there.
    if ! grep -qs 'TELEGRAM_BOT_TOKEN' "$HERMES_HOME/.env" "$HERMES_HOME/config.yaml"; then
        echo "[start] Telegram gateway not started: not configured in $HERMES_HOME."
        echo "[start]   -> run 'hermes gateway setup' in the dev terminal, then restart the Space."
        return 0
    fi
    echo "[start] launching Hermes Telegram gateway (hermes gateway) ..."
    hermes gateway \
        || echo "[start] Hermes gateway exited — is the model (Owl Alpha) configured? ('hermes model')"
}

# Restore Hermes, repair the venv interpreter links + exec bits, then bring up the
# gateway — without blocking uvicorn's port bind.
( ensure_hermes; repair_venv; repair_perms; start_gateway ) &

exec uvicorn app:app --host 0.0.0.0 --port 7860
