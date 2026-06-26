# Autoclipping — Startup Guide (VPS)

A practical, start-to-finish guide to deploying Autoclipping on a **Tencent VPS**
and getting the bot running. It's written for **two readers at once**: each section
opens with a plain-language *"In plain terms"* note, followed by the exact commands
for whoever is at the keyboard. If you only want the big picture, read the *In plain
terms* lines and skip the grey code boxes.

> Deeper technical reference: **`AGENTS.md`** (single source of truth — agents read
> it first). Running status & history: **`PROJECT_STATUS.md`**.
>
> This is the `vps` branch. The `main` branch is the Hugging Face Spaces build.

---

## What this is (the 30-second version)

**In plain terms:** Autoclipping takes a long video, finds the best moments, cuts
them into short vertical clips, and posts them to social media. An AI assistant
called **Hermes** runs the show, and **you talk to it through Telegram** ("Process
this video: …"). It runs in Docker on a VPS you control.

The moving parts:

| Piece | Plain meaning |
|-------|---------------|
| **Tencent VPS** | The server that runs everything (Docker). |
| **Docker Compose** | Starts/stops the app + reverse proxy together. |
| **Hermes Agent** | The AI "brain" that decides what to do and calls the tools. |
| **Tools** (`get_transcript`, `cut_clips`, …) | The five workers that do one job each. |
| **Telegram bot** | Your remote control — how you give it videos and get results. |
| **Caddy** | The doorman: HTTPS + your domain in front of the app. |
| **`hermes-data` volume** | The permanent disk for Hermes' config — survives rebuilds. |

---

## Step 0 — Prepare the VPS (once)

**In plain terms:** install Docker, point your domain at the server, and open the
web ports.

1. Install **Docker + Docker Compose** on the VPS.
2. In your DNS, add an **A record** for your domain → the VPS public IP (and AAAA
   for IPv6 if you have it).
3. In the **Tencent security group / firewall**, open inbound **80** and **443**.

---

## Step 1 — Get the code

**In plain terms:** clone the repo from GitHub and switch to the VPS branch.

```bash
git clone <your-github-repo> autoclipping && cd autoclipping
git checkout vps
```

---

## Step 2 — Add the secret keys

**In plain terms:** the app needs a couple of passwords (API keys) to talk to
outside services. You put them in a local `.env` file (never committed).

```bash
cp .env.example .env
# then edit .env
```

| Name | What it's for |
|------|---------------|
| `FAL_KEY` | The AI that watches video and scores clips (Nemotron via fal). |
| `BLOTATO_API_KEY` | Posting clips to social platforms (Blotato). |
| `BLOTATO_TARGETS` | JSON list of your connected accounts to post to (below). |

**You do NOT need:**
- ❌ An Anthropic key — the text model is **Owl Alpha**, configured inside Hermes.
- ❌ Telegram keys here — those go into **Hermes' own setup** (Step 4), not `.env`.

### Filling in `BLOTATO_TARGETS` (where clips get posted)

**In plain terms:** Blotato won't "post to everything" in one shot — every post must
name a specific connected account. So you give it a **list**: one entry per account
you want to publish to. The app posts each clip to every entry in the list.

It's a JSON array. Each entry needs: your Blotato **`accountId`** (from your Blotato
dashboard), the **`platform`** name, and a **`target`** object. **To add a platform
(e.g. Threads), you add another entry — you don't edit an existing one.**

⚠️ **Not every platform is just `{"targetType": "..."}`.** From Blotato's current spec:

| Platform | `target` needs… | Other notes |
|----------|-----------------|-------------|
| Threads, Instagram, Twitter, Bluesky | just `{"targetType": "<name>"}` | Easiest. Threads allows optional `replyControl`. |
| **TikTok** | `targetType` **plus** `privacyLevel`, `disabledComments`, `disabledDuet`, `disabledStitch`, `isBrandedContent`, `isYourBrand`, `isAiGenerated` | All required, or the post is rejected. |
| **YouTube** | just `targetType` | …plus `title`, `privacyStatus`, `shouldNotifySubscribers` in a **`"content"`** block on the entry (now supported). `title` defaults to the clip caption if omitted. |
| Facebook | `pageId` + `mediaType` | |
| Pinterest | `boardId` | |
| LinkedIn | optional `pageId` | |

Copy-paste starter (swap the placeholder IDs for your real Blotato account IDs).
In `.env` this must be a **single line**:

```
BLOTATO_TARGETS=[{"accountId":"REPLACE_INSTAGRAM_ID","platform":"instagram","target":{"targetType":"instagram"}},{"accountId":"REPLACE_YOUTUBE_ID","platform":"youtube","target":{"targetType":"youtube"},"content":{"privacyStatus":"public","shouldNotifySubscribers":false}},{"accountId":"REPLACE_TIKTOK_ID","platform":"tiktok","target":{"targetType":"tiktok","privacyLevel":"PUBLIC_TO_EVERYONE","disabledComments":false,"disabledDuet":false,"disabledStitch":false,"isBrandedContent":false,"isYourBrand":false,"isAiGenerated":false}}]
```

Rules: **one JSON array** (`[ … ]`), entries comma-separated, **no trailing comma**.
For **YouTube**, the optional `"content"` block carries its required fields
(`privacyStatus`, `shouldNotifySubscribers`); `title` is auto-filled from the clip
caption unless you add your own. TikTok's exact `privacyLevel` value should be
confirmed against Blotato's docs.

---

## Step 3 — Configure the domain + start it

**In plain terms:** tell the doorman (Caddy) your domain, then start everything.
Caddy gets the HTTPS certificate automatically on first run.

Edit **`Caddyfile`** — replace `example.com` with your domain and the email with
yours. Then:

```bash
docker compose up -d --build
```

**What "good" looks like:** the build finishes and both containers stay up
(`docker compose ps`). Hermes is baked into the image, so the health check shows
`"installed"` straight away:

```bash
curl -s https://<your-domain>/
# {"status":"Autoclipping pipeline is live","hermes":"installed"}
```

---

## Step 4 — Configure Hermes (one-time)

**In plain terms:** the AI brain needs three things once: which model to think with,
how to reach you on Telegram, and which tools it's allowed to use. These run inside
the container and are saved to the `hermes-data` volume, so they persist.

**4a. Pick the model** — choose **Owl Alpha** in the picker:

```bash
docker compose exec app hermes model
```

**4b. Connect Telegram** — paste your bot token (from @BotFather) and your numeric
Telegram user ID when asked. This writes them into `/data/.hermes/.env`:

```bash
docker compose exec app hermes gateway setup
```

**4c. Register the tools (MCP)** — Hermes calls the tools through an MCP server.
Add this block to `/data/.hermes/config.yaml` (edit from inside the container, e.g.
`docker compose exec app vi /data/.hermes/config.yaml`):

```yaml
mcp_servers:
  autoclipping:
    command: /usr/local/bin/python
    args: ["/app/mcp_server.py"]
    enabled: true
    tools:
      include: [get_transcript, identify_moments, cut_clips, analyze_clips, publish_clips]
```

**4d. Go live** — restart the app so `start.sh` launches the Telegram gateway now
that the token is set:

```bash
docker compose restart app
```

---

## Step 5 — Check everything's healthy

```bash
docker compose ps                                   # both services Up
docker compose exec app hermes --version            # a version, no errors
docker compose exec app hermes tools                # the five tool names listed
curl -s https://<your-domain>/                       # {"status":"...live","hermes":"installed"}
docker compose logs -f app                           # watch the gateway start
```

---

## Step 6 — Use it

**In plain terms:** message your Telegram bot with a video link, and it does the
rest — confirms, processes, and reports back.

In Telegram:

```
Process this video: <YouTube or Twitch link>
```

Expect a quick confirmation, then a final summary (clip count, virality scores,
where it posted, and the next scheduled slot).

---

## Updating later

```bash
git pull
docker compose up -d --build      # rebuilds app/tool code; Hermes config persists
```

> App/tool code ships via image rebuild. Hermes itself lives in the persistent
> volume, so a rebuild does **not** replace it — to upgrade Hermes, update it from
> inside the container or recreate the `hermes-data` volume (which then re-runs the
> one-time Step 4 setup).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Health shows `"hermes":"installing"` | `hermes` not on PATH in the container | `docker compose exec app which hermes`; confirm the build's Hermes install step succeeded (`docker compose logs app`). |
| `hermes tools` is empty after registering | MCP not reloaded, or `mcp_server.py` errored | restart app, or `/reload-mcp` in a `hermes` session; check `docker compose exec app python -c "import mcp_server"` runs cleanly. |
| Telegram bot silent | Gateway not started or not configured | confirm `hermes gateway setup` was done; `docker compose restart app` and check `docker compose logs app` for "launching Hermes Telegram gateway". |
| HTTPS not working / cert errors | DNS not pointed yet, or 80/443 closed | confirm the A record resolves to the VPS and ports 80/443 are open in the Tencent security group; check `docker compose logs caddy`. |
| Lost Hermes config after a change | The `hermes-data` volume was removed | re-run Step 4. Avoid `docker compose down -v` (the `-v` deletes named volumes). |
