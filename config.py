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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
BLOTATO_API_KEY = os.getenv("BLOTATO_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
