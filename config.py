"""Central configuration.

Loads environment variables (from a local .env in development, or from Hugging
Face Space secrets in production) and exposes them as importable constants so the
rest of the app never reads os.environ directly.
"""

import os

from dotenv import load_dotenv

# In production (HF Spaces) the variables come from Space secrets and this is a
# no-op; locally it reads the .env file next to this module.
load_dotenv()

# Telegram credentials are NOT here — Hermes' built-in gateway owns them and reads
# them from its own /data/.hermes/.env (set via `hermes gateway setup`).
FAL_KEY = os.getenv("FAL_KEY")
BLOTATO_API_KEY = os.getenv("BLOTATO_API_KEY")
