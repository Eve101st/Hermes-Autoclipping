# Autoclipping — Where Things Stand (Plain-English)

*Last updated: June 25, 2026*

## What this project is

Autoclipping is an automation app that runs in the cloud on **Hugging Face Spaces**.
It's packaged with **Docker** (a way to bundle the app so it runs the same
everywhere), and it's set up to be driven by an AI assistant called **Hermes Agent**.

Right now we've finished **Phase 1: the foundation**. Think of it as pouring the
concrete and putting up the frame — the house isn't furnished yet, but the
structure is standing and the lights turn on.

## What's done ✅

- The project lives online at the Space: **devproxa/Autoclipping** (private).
- All the starter files are created and **uploaded** to the Space.
- The app has a simple "are you alive?" page that, when working, replies:
  > "Autoclipping pipeline is live"
- Hermes Agent is set to install automatically when the app builds.
- Secret keys (passwords for the various services) have safe placeholders and are
  kept **out** of the public files.

## What's NOT done yet ⏳

1. **Confirming the build worked.** Uploading the files automatically kicks off a
   "build." We still need to look at the build screen and confirm it finished
   without errors — *especially* the part that installs Hermes Agent, which is the
   most likely thing to trip up.
2. **Adding the real secret keys.** The app currently has placeholders. The real
   keys need to be added in the Space's settings before any real work can happen.
3. **Building the actual features.** Phase 1 is just the skeleton. The real
   logic (turning videos into clips, etc.) comes in Phase 2.

## Your next steps 👉

1. **Check the build.** Go to the Space:
   https://huggingface.co/spaces/devproxa/Autoclipping
   Open the **Logs** tab and look for either a green "Running" status or any red
   error. If you see an error mentioning **Hermes** or **install.sh**, copy it and
   send it over — that's the expected weak spot.
2. **Add your secret keys** in the Space under **Settings → Variables and secrets**:
   `ANTHROPIC_API_KEY`, `FAL_KEY`, `BLOTATO_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`.
3. **When ready, start Phase 2** — the real automation logic.

## Moving to your other computer 💻

You do **not** need to copy this folder by hand. Everything is saved online.
On the new machine, just "download" a fresh copy from the Space (the technical
steps are in `HANDOFF.md`). The only thing that won't come along is the secret-keys
file (`.env`) — that's on purpose, for safety. You'll re-create it from the list
above.

## Where to find the details

- **`HANDOFF.md`** — the full technical version for whoever continues the coding.
- **`README.md`** — short project description shown on the Space page.
