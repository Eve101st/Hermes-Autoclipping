"""Step 4 — publish clips to social platforms via Blotato.

Public API:
    publish_clips(clip_paths, captions) -> list[dict]

For each clip:
    1. Presigned upload  -> POST  https://backend.blotato.com/v2/media/uploads
                            (body {"filename"}) returns {presignedUrl, publicUrl}.
    2. PUT the raw bytes -> presignedUrl.
    3. Create a post     -> POST  https://backend.blotato.com/v2/posts
                            for every configured target, with useNextFreeSlot=true.

Auth: the `blotato-api-key` header, value from config.BLOTATO_API_KEY.

⚠️ Blotato's /v2/posts is PER ACCOUNT — each post needs an `accountId`, a
`platform`, and a `target`. There is no single "post to all connected platforms"
call, so "all platforms" means iterating the targets below. Fill `BLOTATO_TARGETS`
with your connected accounts (or set the BLOTATO_TARGETS env var to the same JSON).
"""

from __future__ import annotations

import json
import mimetypes
import os

import requests

import config

_BASE = "https://backend.blotato.com"
_UPLOAD_URL = f"{_BASE}/v2/media/uploads"
_POSTS_URL = f"{_BASE}/v2/posts"

# One entry per connected social account. Example:
#   {"accountId": "acc_123", "platform": "tiktok",  "target": {"targetType": "tiktok"}}
#   {"accountId": "acc_456", "platform": "youtube", "target": {"targetType": "youtube"}}
# Loaded from the BLOTATO_TARGETS env var (JSON array) if present, else this default.
BLOTATO_TARGETS: list[dict] = json.loads(os.getenv("BLOTATO_TARGETS", "[]"))


def _headers() -> dict:
    if not config.BLOTATO_API_KEY:
        raise RuntimeError(
            "BLOTATO_API_KEY is not set. Add it in the Space's Settings -> "
            "Variables and secrets (or your local .env)."
        )
    return {
        "blotato-api-key": config.BLOTATO_API_KEY,
        "Content-Type": "application/json",
    }


def publish_clips(clip_paths: list[str], captions: list[str]) -> list[dict]:
    """Upload each clip and create a post per configured target."""
    if not clip_paths:
        return []
    if not BLOTATO_TARGETS:
        raise RuntimeError(
            "No BLOTATO_TARGETS configured. Set the BLOTATO_TARGETS env var to a "
            "JSON array of {accountId, platform, target} objects."
        )

    captions = captions or []
    results: list[dict] = []

    for index, clip_path in enumerate(clip_paths):
        caption = captions[index] if index < len(captions) else ""
        media_url = _upload_media(clip_path)

        for target in BLOTATO_TARGETS:
            payload = {
                "post": {
                    "accountId": target["accountId"],
                    "content": {
                        "text": caption,
                        "mediaUrls": [media_url],
                        "platform": target["platform"],
                    },
                    "target": target["target"],
                },
                "useNextFreeSlot": True,
            }
            response = requests.post(
                _POSTS_URL, headers=_headers(), json=payload, timeout=60
            )
            results.append(
                {
                    "clip": clip_path,
                    "platform": target["platform"],
                    "accountId": target["accountId"],
                    "status": response.status_code,
                    "response": _safe_json(response),
                }
            )

    return results


def _upload_media(clip_path: str) -> str:
    """Presigned-upload a local file and return its public Blotato media URL."""
    if not os.path.exists(clip_path):
        raise FileNotFoundError(f"clip not found: {clip_path}")

    filename = os.path.basename(clip_path)
    presign = requests.post(
        _UPLOAD_URL, headers=_headers(), json={"filename": filename}, timeout=60
    )
    presign.raise_for_status()
    data = presign.json()
    presigned_url = data["presignedUrl"]
    public_url = data["publicUrl"]

    mime = mimetypes.guess_type(filename)[0] or "video/mp4"
    with open(clip_path, "rb") as fh:
        put = requests.put(
            presigned_url, data=fh, headers={"Content-Type": mime}, timeout=300
        )
    put.raise_for_status()
    return public_url


def _safe_json(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        return response.text
