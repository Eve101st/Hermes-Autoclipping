"""Central configuration.

Loads environment variables and exposes them as importable constants so the rest
of the app never reads os.environ directly. On the VPS the variables come from the
process environment — Hermes injects the pipeline secrets via its
`mcp_servers.autoclipping.env:` block (see AGENTS.md §6); locally they come from the
.env file next to this module.
"""

import os

from dotenv import load_dotenv

# On the VPS the vars are already in the process environment (Hermes' mcp_servers
# env: block), so this is effectively a no-op; locally it reads the .env file here.
load_dotenv()

# Telegram credentials are NOT here — Hermes' built-in gateway owns them and reads
# them from its own ~/.hermes/.env (set via `hermes gateway setup`).
FAL_KEY = os.getenv("FAL_KEY")
BLOTATO_API_KEY = os.getenv("BLOTATO_API_KEY")

# Residential proxy for YouTube only (yt-dlp + youtube-transcript-api). Datacenter
# IPs (a VPS) get blocked by YouTube, so transcript + VOD download route through
# this. Format: http://user:pass@host:port (e.g. a Geonode rotating residential
# endpoint). Empty -> direct (expect YT IP blocks). fal/Blotato/Telegram do NOT
# use it.
YT_PROXY = os.getenv("YT_PROXY")
