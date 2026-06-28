#!/usr/bin/env bash
# ============================================================================
# Bare-metal host bootstrap for the Autoclipping `vps` branch (migration Part B).
#
# Idempotent. Installs system deps, the project venv, Tor config, the upload dir,
# and the systemd unit files — i.e. everything that can be STAGED ALONGSIDE the
# still-running Docker stack with no conflict.
#
# It deliberately does NOT:
#   - start/enable the services (avoids an 8081 clash with the Docker bot-api and
#     any mid-session cutover) — do that during a maintenance window,
#   - touch Docker (teardown is the LAST step, after bare-metal is verified),
#   - run the one-time Telegram `logOut` (disruptive; manual, see §7 of the prompt),
#   - install Hermes (run `hermes`'s own installer per MIGRATION_BUILD_PROMPT.md §5.3).
#
# Run as a sudo-capable user on the VPS, from a checkout at /opt/autoclipping:
#   sudo bash deploy/install.sh
# ============================================================================
set -euo pipefail

APP_DIR=/opt/autoclipping
RUN_USER=ubuntu
UPLOAD_DIR=/var/lib/telegram-bot-api
# Python: Ubuntu 22.04 ships 3.10 (3.11 is only an RC in its repos). The tools need
# >=3.10 (fastmcp), so prefer the system default 3.10; override by exporting PYTHON.
PYTHON="${PYTHON:-python3.10}"

echo "[install] APP_DIR=$APP_DIR RUN_USER=$RUN_USER PYTHON=$PYTHON"

# --- 1. System dependencies (mirror the old Dockerfile, minus container scaffolding) ---
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  "$PYTHON" "${PYTHON}-venv" python3-pip \
  ffmpeg git ripgrep curl xz-utils ca-certificates tor

# Node.js 22 (Hermes requires >=22.12) — same NodeSource channel the Dockerfile used.
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -dv -f2 | cut -d. -f1)" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y --no-install-recommends nodejs
fi

# uv (Hermes prereq). Installs into the invoking user's home; harmless if present.
if ! command -v uv >/dev/null 2>&1; then
  sudo -u "$RUN_USER" sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

# --- 2. Tor: loopback SOCKS5 on 127.0.0.1:9050 (parity with the old Dockerfile torrc) ---
install -m 0644 /dev/stdin /etc/tor/torrc <<'TORRC'
SocksPort 127.0.0.1:9050
SafeSocks 1
TestSocks 1
TORRC

# --- 3. Project venv (tools only; Hermes keeps its own managed runtime under ~/.hermes) ---
if [ ! -d "$APP_DIR/.venv" ]; then
  sudo -u "$RUN_USER" "$PYTHON" -m venv "$APP_DIR/.venv"
fi
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# --- 4. Upload dir — written by telegram-bot-api, read by the MCP tools. Same uid (D3). ---
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 "$UPLOAD_DIR"

# --- 5. systemd units (installed, NOT enabled — cutover happens in the window) ---
install -m 0644 "$APP_DIR/deploy/systemd/telegram-bot-api.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/hermes-gateway.service" /etc/systemd/system/
systemctl daemon-reload

cat <<'NEXT'

[install] Done staging. NOT started — nothing was enabled and Docker is untouched.

Next (in a maintenance window, bot confirmed idle):
  1. Fill /opt/autoclipping/.env with TELEGRAM_API_ID / TELEGRAM_API_HASH.
  2. Install Hermes (prompt §5.3): curl -fsSL .../install.sh | bash ; then
     `hermes model` (Owl Alpha) and `hermes gateway setup`.
  3. One-time, mandatory: log the bot out of the public API so the local server
     accepts it:  curl "https://api.telegram.org/bot<TOKEN>/logOut"
  4. Hand-edit ~/.hermes/config.yaml per prompt §6 (platforms.telegram.extra +
     mcp_servers.autoclipping.env). Verify: `hermes tools` lists all six.
  5. Stop the Docker stack, then:
       sudo systemctl enable --now tor telegram-bot-api hermes-gateway
  6. Run the acceptance tests (prompt §9). Retire Docker only after they pass.
NEXT
