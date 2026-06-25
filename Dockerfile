FROM python:3.9

# --- System dependencies (installed as root) ---
# Hermes Agent's installer can auto-install these, but it requires root for apt
# and we run it as a non-root user, so pre-install everything it depends on:
# git (required prerequisite), Node.js + npm, ripgrep, ffmpeg, curl.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ripgrep ffmpeg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user with UID 1000 (Hugging Face Spaces requirement) ---
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# --- Python dependencies ---
WORKDIR /app
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Hermes Agent (as the non-root user) ---
# Official installer: https://hermes-agent.nousresearch.com/docs/getting-started/installation
# NOTE: there is no `@nousresearch/hermes-agent` npm package; the documented
# install path is this script, which sets up the global `hermes` command.
USER user
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash < /dev/null

# --- Application code ---
COPY --chown=user:user . .

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
