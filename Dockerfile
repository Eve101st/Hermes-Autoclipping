FROM python:3.9

# --- System dependencies (installed as root) ---
# Hermes is installed at RUNTIME by entrypoint.sh (see that file for why), so the
# image only needs the tools the installer and the app rely on:
#   curl git        - installer download + `git clone` of the Hermes repo
#   xz-utils        - the installer unpacks Node.js from a .tar.xz archive
#   ripgrep         - used by Hermes' code/search tools
#   ffmpeg          - clip cutting / audio extraction (tools/clipper, transcript)
#   Node.js 22      - Hermes requires Node >=22.12 (matches the installer's own
#                     provisioning; pre-installing it makes first boot faster)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git xz-utils ripgrep ffmpeg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user with UID 1000 (Hugging Face Spaces requirement) ---
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # Hermes keeps code + managed Node/uv + config + sessions here. /data is the
    # persistent Space bucket, so everything survives rebuilds.
    HERMES_HOME=/data/.hermes

# --- Python dependencies ---
WORKDIR /app
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ---
COPY --chown=user:user . .
RUN chmod +x entrypoint.sh

USER user

EXPOSE 7860
# entrypoint.sh restores Hermes into /data (background) then execs uvicorn.
CMD ["./entrypoint.sh"]
