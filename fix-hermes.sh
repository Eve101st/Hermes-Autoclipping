#!/usr/bin/env bash
# ============================================================================
# fix-hermes.sh — fully repair the `hermes` command in a Dev Mode terminal.
#
# Dev Mode does NOT run start.sh, and reloads reset the ephemeral home. Worse,
# the venv's python interpreter symlinks (python/python3/python3.11) and the +x
# bits sometimes go missing on /data. This script repairs all of it, idempotently:
#   1. recreate the three venv python interpreter links (against the image Python)
#   2. re-apply the execute bits the FUSE mount drops
#   3. put the venv's bin directly on PATH (robust — no $HOME dependency)
#
# SOURCE it so the PATH change sticks in your shell:
#     . /app/fix-hermes.sh        (sh)   or   source /app/fix-hermes.sh   (bash)
# ============================================================================
export HERMES_HOME=/data/.hermes
_VBIN="$HERMES_HOME/hermes-agent/venv/bin"

if [ ! -e "$_VBIN/hermes" ]; then
    echo "[fix-hermes] No Hermes at $_VBIN/hermes — do a one-time full install:"
    echo "[fix-hermes]   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive"
else
    # 1. venv python interpreter links (the shebang target) — idempotent.
    _base="/usr/local/bin/python3.11"
    [ -x "$_base" ] || _base="$(command -v python3.11 || command -v python3)"
    if [ -n "$_base" ]; then
        ln -sfn "$_base"    "$_VBIN/python3.11"
        ln -sfn python3.11  "$_VBIN/python3"
        ln -sfn python3     "$_VBIN/python"
    fi

    # 2. execute bits (guard each dir so a missing one doesn't abort the rest).
    chmod -R u+x "$_VBIN" 2>/dev/null
    [ -d "$HERMES_HOME/bin" ]      && chmod -R u+x "$HERMES_HOME/bin" 2>/dev/null
    [ -d "$HERMES_HOME/node/bin" ] && chmod -R u+x "$HERMES_HOME/node/bin" 2>/dev/null

    # 3. PATH — point straight at the venv bin (no reliance on ~/.local/bin).
    case ":$PATH:" in
        *":$_VBIN:"*) ;;
        *) export PATH="$_VBIN:$PATH" ;;
    esac

    if hermes --version >/dev/null 2>&1; then
        echo "[fix-hermes] OK: $(hermes --version 2>/dev/null | head -1)"
    else
        echo "[fix-hermes] Still broken. Paste: $_VBIN/hermes --version"
    fi
fi
