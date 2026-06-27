"""Central configuration.

Loads environment variables and exposes them as importable constants so the rest
of the app never reads os.environ directly. In production (VPS) the variables come
from docker-compose `env_file: .env` (the process environment); locally they come
from the .env file next to this module.
"""

import os

from dotenv import load_dotenv

# In the container the vars are already in the environment (compose env_file), so
# this is effectively a no-op; locally it reads the .env file next to this module.
load_dotenv()

# Telegram credentials are NOT here — Hermes' built-in gateway owns them and reads
# them from its own /data/.hermes/.env (set via `hermes gateway setup`).
FAL_KEY = os.getenv("FAL_KEY")
BLOTATO_API_KEY = os.getenv("BLOTATO_API_KEY")

# Residential proxy for YouTube only (yt-dlp + youtube-transcript-api). Datacenter
# IPs (a VPS) get blocked by YouTube, so transcript + VOD download route through
# this. Format: http://user:pass@host:port (e.g. a Geonode rotating residential
# endpoint). Empty -> direct (expect YT IP blocks). fal/Blotato/Telegram do NOT
# use it.
YT_PROXY = os.getenv("YT_PROXY")
