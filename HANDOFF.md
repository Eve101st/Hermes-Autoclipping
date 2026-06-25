# Autoclipping — Developer Handoff

**Last updated:** 2026-06-25
**Phase:** 1 (infrastructure scaffold) — pushed, build verification pending
**Maintainer:** devproxa (evedarkness18@gmail.com)

---

## 1. Repository / hosting

| Property | Value |
|----------|-------|
| Host | Hugging Face Spaces |
| Repo URL | `https://huggingface.co/spaces/devproxa/Autoclipping` |
| Visibility | **Private** |
| Space SDK | `docker` (see `README.md` frontmatter) |
| App port | `7860` (`app_port: 7860` in README, `EXPOSE 7860` in Dockerfile) |
| Default branch | `main` |
| Base commit | `3df67d5` (HF auto-created "initial commit") |
| Scaffold commit | `fc6104f` — "Scaffold Phase 1: FastAPI app, Docker build, Hermes Agent install, config" |

## 2. Git authentication (how pushes work)

- Protocol: **HTTPS** (not SSH).
- Credential: a **fine-grained HF access token** with **Write access to contents/settings** for this repo, used as the git password.
- Username at the prompt: `devproxa`. Password: the token.
- Storage: **Git Credential Manager** → Windows Credential Manager (`git config --global credential.helper manager`). The token is **not** stored in any repo file and is **not** in git history.
- On a new machine you must re-authenticate once (the credential store does not travel with the repo). See §7.

## 3. Files in the repo (committed)

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app. `GET /` returns `{"status": "Autoclipping pipeline is live", "hermes": "installed"}`. |
| `config.py` | Loads env vars via `python-dotenv` (`load_dotenv()`) and exposes 5 constants: `ANTHROPIC_API_KEY`, `FAL_KEY`, `BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `youtube-transcript-api`, `faster-whisper`, `httpx`, `python-dotenv`, `fal-client`, `requests`. |
| `Dockerfile` | Build definition — see §4. |
| `README.md` | HF Space frontmatter (`sdk: docker`, `app_port: 7860`) + project notes. |
| `.gitattributes` | HF Git-LFS binary patterns **+** `* text=auto eol=lf` (forces LF for the Linux builder). |
| `.gitignore` | Ignores `.env`, `.claude/`, Python caches. |
| `.dockerignore` | Keeps `.env`, `.git`, caches out of the image build context. |

## 4. Dockerfile design (and why)

- Base: `python:3.9` (Debian Bullseye).
- **System deps installed as root** before dropping privileges, because the Hermes installer needs them and cannot `apt` as a non-root user:
  `curl git ripgrep ffmpeg ca-certificates` + **Node.js 20 via NodeSource** + `nodejs` (includes npm).
- **Non-root user UID 1000** (`useradd -m -u 1000 user`) — HF Spaces requirement. `HOME=/home/user`, `PATH` includes `/home/user/.local/bin`.
- Python deps installed from `requirements.txt`.
- **Hermes Agent install (as the non-root user):**
  `RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash < /dev/null`
- App copied to `/app`, `EXPOSE 7860`, `CMD ["uvicorn","app:app","--host","0.0.0.0","--port","7860"]`.

## 5. Deviations from the original spec (important)

1. **`@nousresearch/hermes-agent` npm package does NOT exist** (npm registry returns 404). Hermes Agent is installed via its official `install.sh` script instead (per https://hermes-agent.nousresearch.com/docs/getting-started/installation). GitHub source: `NousResearch/hermes-agent`.
2. **`nodejs` and `npm` removed from `requirements.txt`** — they are not the real Node runtime on PyPI; Node is installed via apt/NodeSource in the Dockerfile.
3. **Step 1 "clone" adaptation** — files were authored first, then HF's `.git` was adopted to make the folder a real clone (history: `3df67d5` → `fc6104f`).
4. **Added** `README.md` (frontmatter is mandatory for a Docker Space to build), merged `.gitattributes`, and `.dockerignore`.

## 6. Known risks / open items (verify in build logs)

1. **Hermes `install.sh` during build (HIGHEST RISK):** the installer is designed for interactive setup (LLM provider config). `< /dev/null` is used to avoid a stdin hang, but it may need a non-interactive flag/env var, or may need to be split (pin a release / clone `NousResearch/hermes-agent` directly). This is the most likely build failure.
2. **`"hermes": "installed"` in `app.py` is hardcoded** — it does not probe the binary. Recommended Phase-2 fix: shell out to `hermes --version` (or check the binary on `PATH`) so the health check is truthful.
3. **Space secrets not yet set** — `config.py` will read `None` for all keys until the 5 secrets are added in the Space (Settings → Variables and secrets).

## 7. Continuing on a new machine (clone into a fresh VS Code project)

> **Hosting note:** the git remote is the **Hugging Face Space** — this is the
> single source of truth. **Do NOT push to GitHub.** The GitHub account associated
> with the Space belongs to the **client**, not the maintainer. Do not add a
> GitHub remote; use the HF `origin` only.

**Do NOT zip the folder — clone it.**

### Prerequisites on the new machine
- [Git](https://git-scm.com/download/win) (includes Git Credential Manager)
- [VS Code](https://code.visualstudio.com/)
- Python 3.9+ (for running/editing locally)
- *(Optional)* Docker Desktop — only if you want to build/run the container locally
- VS Code extensions (recommended): **Python**, **Docker**

### Option A — clone from inside VS Code (GUI)
1. Open VS Code → `Ctrl+Shift+P` → **Git: Clone**.
2. Paste: `https://huggingface.co/spaces/devproxa/Autoclipping`
3. Pick a local folder; when prompted, **Open** the cloned repo.
4. Authenticate when asked: **username** `devproxa`, **password** = your HF
   **write** access token (https://huggingface.co/settings/tokens).

### Option B — clone from the terminal, then open in VS Code
```bash
git clone https://huggingface.co/spaces/devproxa/Autoclipping
cd Autoclipping
code .
```
Same credentials as above when prompted.

### After cloning (either option)
1. **Recreate `.env`** — it is gitignored, so it is NOT in the clone. Create a new
   `.env` in the project root with these keys (values come from §3 / `config.py`):
   ```
   ANTHROPIC_API_KEY=
   FAL_KEY=
   BLOTATO_API_KEY=
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_ID=
   ```
2. *(Optional)* Run locally without Docker:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows  (use: source .venv/bin/activate on macOS/Linux)
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 7860
   ```
3. Make changes → `git add` / `git commit` / `git push origin main`. Pushing to the
   HF remote redeploys the Space automatically.

## 8. Next actions (Phase 2 entry)

1. Verify the Docker build succeeds on HF (focus on the Hermes `install.sh` step).
2. Add the 5 Space secrets.
3. Make the `/` health check actually verify Hermes.
4. Begin pipeline logic (transcript fetch → whisper → clip selection → render → publish/notify).
