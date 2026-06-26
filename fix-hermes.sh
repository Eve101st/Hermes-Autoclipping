#!/usr/bin/env bash
# ============================================================================
# fix-hermes.sh — restore the `hermes` command after a Dev Mode reload.
#
# Why this exists:
#   HF **Dev Mode** does NOT run start.sh, and reloading the web VS Code / dev
#   container resets the ephemeral home (/home/user). That wipes the `hermes`
#   symlink and the PATH entry, so `hermes` suddenly becomes "not found". The
#   ACTUAL install lives on persistent /data and is intact — so a full reinstall
#   is unnecessary, and over the /data FUSE mount it often fails anyway.
#
#   This script just re-links the command, re-applies the execute bits the FUSE
#   mount drops, and fixes PATH. No network, no reinstall.
#
# Usage — SOURCE it so the PATH change sticks in your shell:
#     source /app/fix-hermes.sh
# ============================================================================
export HERMES_HOME=/data/.hermes
_HB="$HERMES_HOME/hermes-agent/venv/bin/hermes"

if [ ! -e "$_HB" ]; then
    echo "[fix-hermes] No Hermes install found at $_HB."
    echo "[fix-hermes] Do a one-time full install instead:"
    echo "[fix-hermes]   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive"
else
    chmod -R u+x "$HERMES_HOME/hermes-agent/venv/bin" "$HERMES_HOME/bin" "$HERMES_HOME/node/bin" 2>/dev/null
    mkdir -p "$HOME/.local/bin"
    ln -sf "$_HB" "$HOME/.local/bin/hermes"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) export PATH="$HOME/.local/bin:$PATH" ;;
    esac
    if hermes --version >/dev/null 2>&1; then
        echo "[fix-hermes] OK: $(hermes --version 2>/dev/null | head -1)"
    else
        echo "[fix-hermes] Relinked, but hermes still won't run. Paste: $_HB --version"
    fi
fi
