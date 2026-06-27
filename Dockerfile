FROM python:3.11

# --- System dependencies (installed as root) ---
#   curl git        - Hermes installer download + its `git clone`
#   xz-utils        - the installer unpacks Node.js from a .tar.xz archive
#   ripgrep         - used by Hermes' code/search tools
#   ffmpeg          - clip cutting / audio extraction (tools/clipper, transcript)
#   Node.js 22      - Hermes requires Node >=22.12
#   tor             - SOCKS5 proxy so yt-dlp / transcript traffic exits via Tor
#                     exit nodes (not the datacenter IP), bypassing proxy-provider
#                     throttling on YouTube video downloads.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git xz-utils ripgrep ffmpeg ca-certificates tor \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Tor: SOCKS5 on 127.0.0.1:9050 (no local network exposure — loopback only).
RUN printf 'SocksPort 127.0.0.1:9050\nSafeSocks 1\nTestSocks 1\n' \
        > /etc/tor/torrc \
    && chmod 644 /etc/tor/torrc

# --- Non-root user (hygiene; not required on a VPS, kept to avoid running as root) ---
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/data/.hermes/hermes-agent/venv/bin:/home/user/.local/bin:$PATH \
    HERMES_HOME=/data/.hermes

# --- Hermes baked into the image at build time ---
# Unlike Hugging Face (where /data is a runtime-only FUSE mount, forcing a runtime
# install + exec-bit repairs), a VPS has a real filesystem so we install Hermes
# during the build. We install into /data/.hermes; at runtime a docker named volume
# mounted at /data is auto-SEEDED from this baked content the first time it's empty,
# then persists across rebuilds (see docker-compose.yml).
#   NOTE: because a non-empty volume is NOT re-seeded, rebuilding the image with a
#   newer Hermes will NOT replace the Hermes already in an existing volume — upgrade
#   Hermes from inside the container, or recreate the volume. App code under /app is
#   not on the volume, so app/tool changes ship normally via image rebuild.
RUN mkdir -p /data/.hermes && chown -R user:user /data
USER user
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
        | bash -s -- --skip-setup --skip-browser --non-interactive

# --- Python dependencies ---
USER root
WORKDIR /app
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ---
COPY --chown=user:user . .
RUN chmod +x start.sh

USER user

EXPOSE 7860
# start.sh launches the Telegram gateway (if configured) in the background, then
# execs uvicorn (foreground). Hermes is already present (baked + volume-seeded).
CMD ["./start.sh"]
