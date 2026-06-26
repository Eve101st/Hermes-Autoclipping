"""Step 2 — clip analysis via NVIDIA Nemotron 3 Nano Omni on fal.

Public API:
    identify_moments(transcript)  -> list[{"start", "end", "reason"}]   (top 5)
    analyze_clips(clip_paths)     -> list[{"clip", "start", "end",
                                           "caption", "virality_score"}]

`identify_moments` reasons over the transcript *text* (text endpoint).
`analyze_clips` reasons over each rendered clip *video* (video endpoint); each
local clip is uploaded to fal first to obtain a `video_url`.

fal endpoint IDs + schema (verified against the fal Nemotron API docs):
    text  : nvidia/nemotron-3-nano-omni   in {prompt}                  -> out {output, finish_reason, usage}
    video : nvidia/nemotron-3-nano-omni/video   in {prompt, video_url} -> out {output, finish_reason, usage}

⚠️ The video endpoint accepts **mp4, up to 1080p, max 2 minutes**. So the candidate
windows from `identify_moments` are capped at ~2 minutes (NOT the original 5) — a
longer clip would be rejected. Cut clips must also be mp4 (clipper already emits mp4).
"""

from __future__ import annotations

import json
import os
import re

import config

TEXT_ENDPOINT = "nvidia/nemotron-3-nano-omni"
VIDEO_ENDPOINT = "nvidia/nemotron-3-nano-omni/video"
_VIDEO_INPUT_KEY = "video_url"


def _ensure_fal_key() -> None:
    """fal_client reads FAL_KEY from the environment; make sure it's there."""
    if not config.FAL_KEY:
        raise RuntimeError(
            "FAL_KEY is not set. Add it in the Space's Settings -> Variables and "
            "secrets (or your local .env)."
        )
    os.environ.setdefault("FAL_KEY", config.FAL_KEY)


def identify_moments(transcript: str) -> list[dict]:
    """Return the ten most clip-worthy windows (each <=2 min) from a VOD transcript.

    Each window is capped at ~115 s: clipper adds a 2-second lead buffer at cut
    time and the downstream Nemotron *video* endpoint hard-caps at 2 minutes.
    The model is told to put start/end on sentence boundaries (never mid-sentence)
    and to confirm that in each window's `reason`.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript is empty")
    _ensure_fal_key()
    import fal_client

    prompt = (
        "You are a short-form video producer. Below is a timestamped transcript "
        "([HH:MM:SS] per line) of a long VOD. Identify the TEN most clip-worthy "
        "windows (high energy, emotional, funny, surprising, or insightful).\n\n"
        "BOUNDARY RULES (critical):\n"
        "- Each window MUST be no longer than ~115 seconds. A 2-second lead buffer "
        "is added at cut time and the analysis model hard-caps at 2 minutes, so "
        "keep each window under ~115s.\n"
        "- `start` and `end` MUST fall on NATURAL sentence boundaries / clear "
        "pauses — NEVER mid-sentence. Inspect the transcript line at your chosen "
        "`start`: if a sentence is already in progress there, move `start` earlier "
        "to the beginning of that sentence. Do the same so `end` lands at a "
        "sentence's end.\n"
        "- In each object's `reason`, explicitly confirm the cut does not begin or "
        "end mid-sentence (e.g. 'starts at a sentence boundary after a pause').\n\n"
        "Respond with ONLY a JSON array of exactly 10 objects, no prose, each:\n"
        '{"start": "HH:MM:SS", "end": "HH:MM:SS", '
        '"reason": "<why it is clip-worthy + boundary confirmation>"}\n\n'
        "TRANSCRIPT:\n"
        f"{transcript}"
    )

    result = fal_client.subscribe(
        TEXT_ENDPOINT, arguments={"prompt": prompt}, with_logs=False
    )
    moments = _extract_json(result.get("output", ""))
    if not isinstance(moments, list):
        raise ValueError(f"unexpected model output: {result.get('output')!r}")
    return moments[:10]


def analyze_clips(clip_paths: list[str]) -> list[dict]:
    """For each rendered clip, pick the best 30-90s moment + caption + score.

    Each clip must be mp4, <=1080p, <=2 minutes (Nemotron video-endpoint limits).
    """
    if not clip_paths:
        return []
    _ensure_fal_key()
    import fal_client

    prompt = (
        "Watch this short video clip. Pick the single best 30-90 second moment for "
        "a vertical short-form post. Respond with ONLY a JSON object, no prose:\n"
        '{"start": "MM:SS", "end": "MM:SS", "caption": "<scroll-stopping caption '
        'with hashtags>", "virality_score": <integer 0-100>}'
    )

    results: list[dict] = []
    for path in clip_paths:
        video_url = fal_client.upload_file(path)
        result = fal_client.subscribe(
            VIDEO_ENDPOINT,
            arguments={"prompt": prompt, _VIDEO_INPUT_KEY: video_url},
            with_logs=False,
        )
        data = _extract_json(result.get("output", ""))
        if not isinstance(data, dict):
            data = {"start": None, "end": None, "caption": "", "virality_score": 0}
        data["clip"] = path
        results.append(data)
    return results


def _extract_json(text: str):
    """Best-effort JSON extraction from model output (handles ```json fences)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} or [...] block in the text.
    match = re.search(r"(\[.*\]|\{.*\})", candidate, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None
