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

# --- Tor SOCKS5 proxy (for yt-dlp / transcript downloads) ---
# YouTube throttles known datacenter IPs (and our old residential proxy was
# throttled to ~10KB/s). Route outbound traffic for the pipeline tools through
# Tor exit nodes so YouTube sees a non-datacenter IP. Loopback-only — not
# exposed on the container network.
start_tor() {
    if ! command -v tor >/dev/null 2>&1; then
        echo "[start] Tor not installed — skipping SOCKS5 proxy."
        return 0
    fi
    echo "[start] launching Tor SOCKS5 proxy on 127.0.0.1:9050 (daemon) ..."
    # --runasdaemon 1 forks Tor into the background and returns; with 0 it would
    # block start.sh and uvicorn would never come up.
    tor --runasdaemon 1 >/dev/null 2>&1 \
        || echo "[start] Tor failed to start (continuing — Smartproxy is primary)."
}
stop_tor() {
    if command -v tor >/dev/null 2>&1; then
        pkill -x tor 2>/dev/null || true
    fi
}

start_tor
# Tor is kept SCOPED to the YouTube tools via the dedicated TOR_PROXY var (each
# tool's _proxy() reads YT_PROXY first, then TOR_PROXY). It is deliberately NOT
# exported as ALL_PROXY/HTTPS_PROXY/HTTP_PROXY, so fal / Blotato / Telegram /
# Owl Alpha traffic stays DIRECT — routing those through Tor would be slow and is
# often blocked by those services.

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
