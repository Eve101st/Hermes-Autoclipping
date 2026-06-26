# Autoclipping — Startup Guide

A practical, start-to-finish guide to deploying the Space and getting the bot
running. It's written for **two readers at once**: each section opens with a
plain-language *"In plain terms"* note, followed by the exact commands for whoever
is at the keyboard. If you only want the big picture, read the *In plain terms*
lines and skip the grey code boxes.

> Deeper technical reference: **`AGENTS.md`** (single source of truth — agents read
> it first). Running status & history:
> **`PROJECT_STATUS.md`**.

---

## What this is (the 30-second version)

**In plain terms:** Autoclipping is an app that lives in the cloud (on Hugging Face
"Spaces"). It takes a long video, finds the best moments, cuts them into short
vertical clips, and posts them to social media. An AI assistant called **Hermes**
runs the show, and **you talk to it through Telegram** ("Process this video: …").

The moving parts:

| Piece | Plain meaning |
|-------|---------------|
| **Hugging Face Space** | The computer in the cloud that runs everything. |
| **Hermes Agent** | The AI "brain" that decides what to do and calls the tools. |
| **Tools** (`get_transcript`, `cut_clips`, …) | The five workers that do one job each. |
| **Telegram bot** | Your remote control — how you give it videos and get results. |
| **`/data`** | The Space's permanent hard drive — survives restarts. |

---

## Step 1 — Deploy (push the code)

**In plain terms:** "Deploying" just means pushing the code. The cloud notices and
rebuilds itself automatically — you don't click anything.

```bash
git push origin main      # this redeploys the Space
```

Then open the Space and watch it build:
`https://huggingface.co/spaces/devproxa/Autoclipping` → **Logs** tab.

**What "good" looks like:** the build finishes, the status turns **Running**, and
the logs show Hermes installing into `/data`. Opening the Space URL shows:
`{"status":"Autoclipping pipeline is live","hermes":"installing"}` — which flips to
`"installed"` a minute or two later.

---

## Step 2 — Add the secret keys

**In plain terms:** the app needs a couple of passwords (API keys) to talk to
outside services. You paste them into the Space's settings, not into any file.

Go to **Settings → Variables and secrets** (owner account only):
`https://huggingface.co/spaces/devproxa/Autoclipping/settings`

| Name | Type | What it's for |
|------|------|---------------|
| `FAL_KEY` | Secret | The AI that watches video and scores clips (Nemotron via fal). |
| `BLOTATO_API_KEY` | Secret | Posting clips to social platforms (Blotato). |
| `BLOTATO_TARGETS` | Variable | JSON list of your connected accounts to post to. |

**You do NOT need:**
- ❌ An Anthropic key — the text model is **Owl Alpha**, configured inside Hermes.
- ❌ Telegram keys here — those go into **Hermes' own setup** (Step 3), not Space secrets.

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

Copy-paste starter (swap the placeholder IDs for your real Blotato account IDs):

```json
[
  {"accountId": "REPLACE_INSTAGRAM_ID", "platform": "instagram", "target": {"targetType": "instagram"}},
  {"accountId": "REPLACE_THREADS_ID",   "platform": "threads",   "target": {"targetType": "threads"}},
  {"accountId": "REPLACE_YOUTUBE_ID",   "platform": "youtube",   "target": {"targetType": "youtube"},
    "content": {"privacyStatus": "public", "shouldNotifySubscribers": false}},
  {"accountId": "REPLACE_TIKTOK_ID",    "platform": "tiktok",    "target": {
      "targetType": "tiktok",
      "privacyLevel": "PUBLIC_TO_EVERYONE",
      "disabledComments": false, "disabledDuet": false, "disabledStitch": false,
      "isBrandedContent": false, "isYourBrand": false, "isAiGenerated": false
  }}
]
```

Rules: the whole thing is **one JSON array** (`[ … ]`), entries comma-separated, **no
trailing comma**. For **YouTube**, the optional `"content"` block carries its required
fields (`privacyStatus`, `shouldNotifySubscribers`); `title` is auto-filled from the
clip caption unless you add your own. TikTok's exact `privacyLevel` value should be
confirmed against Blotato's docs.

---

## Step 3 — Configure Hermes (one-time, in the terminal)

**In plain terms:** the AI brain needs to be told three things once: which model to
think with, how to reach you on Telegram, and which tools it's allowed to use. This
is done in a terminal inside the Space.

Turn on **Dev Mode** (Settings → Dev Mode) and open its terminal (or SSH/VS Code).

> ⚠️ **Heads-up about Dev Mode:** in Dev Mode the Space gives you a terminal but
> does **not** run the normal startup script (`start.sh`). So Hermes' command may
> not be wired up yet, and a quirk of the cloud disk means its program file can lose
> its "runnable" flag. The one line below fixes both. (On a normal, non-Dev boot,
> `start.sh` does this for you automatically.)

**3a. Make the `hermes` command runnable.** Simplest — one command (and re-run this
**any time `hermes` goes "not found" after a Dev Mode / VS Code reload**):

```bash
source /app/fix-hermes.sh
```

That relinks Hermes from the persistent `/data` install and repairs perms — **no
reinstall** (reinstalling over the FUSE mount tends to fail). The equivalent manual
one-liner, if you prefer:

```bash
chmod -R u+x /data/.hermes/hermes-agent/venv/bin /data/.hermes/bin /data/.hermes/node/bin && ln -sf /data/.hermes/hermes-agent/venv/bin/hermes "$HOME/.local/bin/hermes" && export PATH="$HOME/.local/bin:$PATH" && hermes --version
```

Expect a version number. Only if `/data/.hermes/hermes-agent` is genuinely missing
(not just "not found") do a one-time full install — safe to repeat:

```bash
export HERMES_HOME=/data/.hermes; curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser --non-interactive && chmod -R u+x /data/.hermes/hermes-agent/venv/bin /data/.hermes/bin /data/.hermes/node/bin && hermes --version
```

**3b. Pick the model** — choose **Owl Alpha** in the picker:

```bash
hermes model
```

**3c. Connect Telegram** — paste your bot token (from @BotFather) and your numeric
Telegram user ID when asked. This writes them into Hermes' own `/data/.hermes/.env`:

```bash
hermes gateway setup
```

**3d. Register the tools (MCP)** — Hermes calls the tools through an MCP server.
Add this block to `/data/.hermes/config.yaml`:

```yaml
mcp_servers:
  autoclipping:
    command: /usr/local/bin/python
    args: ["/app/mcp_server.py"]
    enabled: true
    tools:
      include: [get_transcript, identify_moments, cut_clips, analyze_clips, publish_clips]
```

Then load it and confirm all five tools appear:

```bash
hermes   # then inside the session: /reload-mcp
hermes tools
```

**3e. Go live** — turn **Dev Mode off** (or restart the Space). On the normal boot,
`start.sh` re-installs/repairs Hermes and **auto-starts the Telegram bot**.

---

## Step 4 — Check everything's healthy

**In plain terms:** a few quick commands to confirm each piece is alive. Run them in
the Space terminal.

```bash
python --version                 # expect 3.11.x  (confirms the current image)
hermes --version                 # expect a version, no "Permission denied"
curl -s localhost:7860/          # expect {"status":"...live","hermes":"installed"}
hermes tools                     # expect the five tool names listed
```

---

## Step 5 — Use it

**In plain terms:** message your Telegram bot with a video link, and it does the
rest — confirms, processes, and reports back.

In Telegram:

```
Process this video: <YouTube or Twitch link>
```

Expect a quick confirmation, then a final summary (clip count, virality scores,
where it posted, and the next scheduled slot).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `hermes: not found` **after a Dev Mode / VS Code reload** (recurring) | Reload reset ephemeral `/home/user`, wiping the symlink + PATH. The install on `/data` is fine. | **`source /app/fix-hermes.sh`** — relinks in one command. **Do NOT reinstall** (it often fails over the FUSE mount). |
| `hermes: cannot execute: Permission denied` | Cloud disk dropped the file's "runnable" flag | `source /app/fix-hermes.sh` (or re-run the **3a** one-liner). Auto-fixed by `start.sh` on a normal boot. |
| Reinstalling Hermes in the dev terminal **fails** | The full installer fights the existing `/data` install over the FUSE mount | You don't need it — `source /app/fix-hermes.sh` instead. Only do a full install if `/data/.hermes/hermes-agent` is truly gone. |
| `python --version` still shows **3.9** | Old image still running | **Settings → Factory reboot** (keeps `/data`, so your config is safe). |
| Health shows `"hermes":"installing"` | Background install not finished | Wait 1–2 min and re-check. |
| `hermes tools` is empty after registering | MCP not reloaded, or `mcp_server.py` errored | `/reload-mcp`; check `python -c "import mcp_server"` runs cleanly. |
| Telegram bot silent | Gateway not started or not configured | Confirm `hermes gateway setup` done; restart with Dev Mode off so `start.sh` launches `hermes gateway`. |

> **Factory reboot is safe:** it rebuilds the image and clears *temporary* storage,
> but **does not delete `/data`** — your Hermes config (Owl Alpha, Telegram, tool
> registration) survives. Deleting `/data` is a separate, explicit action.
