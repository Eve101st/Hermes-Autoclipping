"""Step 3 — cut clips and convert to 9:16 vertical.

Public API:
    cut_clips(video_path, timestamps) -> list[str]

``video_path`` is a LOCAL video file — a Telegram upload. Source videos are always
sent to the bot as files; downloading them from YouTube is unviable (cost +
near-instant throttling), so there is no URL-download path here. (The transcript
tool is the only thing that talks to YouTube, for cheap text transcripts.)

``timestamps`` is a list of dicts with ``start`` and ``end`` (each either seconds or
an "HH:MM:SS"/"MM:SS" string); extra keys such as ``reason``/``caption`` are ignored.
Each window is center-cropped to 1080x1920 (9:16) with ffmpeg and written to
``/tmp/clips``. Returns the list of output paths.
"""

from __future__ import annotations

import os
import subprocess

from ._timecode import to_seconds

OUTPUT_DIR = "/tmp/clips"

# Start each cut this many seconds BEFORE the targeted start, so we don't begin a
# clip in the middle of someone's sentence. Clamped at 0 for the start of the video.
LEAD_BUFFER_SECONDS = 2.0

# scale up so the shorter side covers the 9:16 frame, then center-crop to exact
# 1080x1920. Keeps the action centered without letterboxing.
_VERTICAL_FILTER = (
    "scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920"
)


def _ffmpeg_cut(src: str, start: float, duration: float, out_path: str) -> None:
    """ffmpeg-cut [start, start+duration] from ``src`` to a 9:16 mp4 at ``out_path``."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", src,
        "-t", f"{duration:.3f}",
        "-vf", _VERTICAL_FILTER,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def cut_clips(video_path: str, timestamps: list[dict]) -> list[str]:
    """Cut the given windows out of a LOCAL video file to 9:16 mp4s.

    ``video_path`` is a local file (a Telegram upload). Each timestamp dict has
    ``start``/``end`` (seconds or HH:MM:SS). Returns the output clip paths in
    /tmp/clips. Audio+video stay together — ffmpeg crops each window as-is. Each cut
    starts LEAD_BUFFER_SECONDS early (clamped at 0) so a clip never opens mid-sentence.
    """
    if not video_path:
        raise ValueError("video_path is required")
    if not os.path.isfile(video_path):
        raise ValueError(
            f"video_path must be a local video file (a Telegram upload); got "
            f"{video_path!r}. Source videos are uploaded to the bot, not downloaded "
            f"from a URL."
        )
    if not timestamps:
        return []

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    outputs: list[str] = []
    index = 0
    for window in timestamps:
        start = to_seconds(window.get("start", 0))
        end = to_seconds(window.get("end", 0))
        if end - start <= 0:
            continue
        buffered_start = max(0.0, start - LEAD_BUFFER_SECONDS)
        out_path = os.path.join(OUTPUT_DIR, f"clip_{index:03d}.mp4")
        _ffmpeg_cut(video_path, buffered_start, end - buffered_start, out_path)
        outputs.append(out_path)
        index += 1
    return outputs
