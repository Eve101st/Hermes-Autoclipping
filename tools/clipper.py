"""Step 3 — cut clips and convert to 9:16 vertical.

Public API:
    cut_clips(video_path, timestamps) -> list[str]

`timestamps` is a list of dicts with `start` and `end` (each either seconds or an
"HH:MM:SS"/"MM:SS" string); extra keys such as `reason`/`caption` are ignored.

Uses the `ffmpeg` already shipped in the image (the spec's "HyperFrames" was
unverified; ffmpeg is the standard tool for exact-timestamp extraction). Each
segment is re-encoded and center-cropped to 1080x1920 (9:16) and written to
``/tmp/clips``. Returns the list of output paths.
"""

from __future__ import annotations

import os
import subprocess

from ._timecode import to_seconds

OUTPUT_DIR = "/tmp/clips"

# Start each cut this many seconds BEFORE the targeted start, so we don't begin a
# clip in the middle of someone's sentence. Clamped at 0 for the start of the VOD.
LEAD_BUFFER_SECONDS = 2.0

# scale up so the shorter side covers the 9:16 frame, then center-crop to exact
# 1080x1920. Keeps the action centered without letterboxing.
_VERTICAL_FILTER = (
    "scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920"
)


def cut_clips(video_path: str, timestamps: list[dict]) -> list[str]:
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"video_path not found: {video_path}")
    if not timestamps:
        return []

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outputs: list[str] = []

    for index, window in enumerate(timestamps):
        start = to_seconds(window.get("start", 0))
        end = to_seconds(window.get("end", 0))
        if end - start <= 0:
            continue

        # Pull the start back by the lead buffer (clamped at 0) so the clip doesn't
        # open mid-sentence; the end is left where the model placed it.
        buffered_start = max(0.0, start - LEAD_BUFFER_SECONDS)
        duration = end - buffered_start

        out_path = os.path.join(OUTPUT_DIR, f"clip_{index:03d}.mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{buffered_start:.3f}",   # fast input seek (incl. lead buffer)
            "-i", video_path,
            "-t", f"{duration:.3f}",
            "-vf", _VERTICAL_FILTER,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-movflags", "+faststart",
            out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        outputs.append(out_path)

    return outputs
