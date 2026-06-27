"""VOD download — fetch a source video to a local mp4 for cutting.

Public API:
    download_video(video_url) -> str   # local mp4 path

Closes the pipeline gap where ``cut_clips`` needs a local video file but nothing
fetched it (the orchestrator previously had to shell out to yt-dlp by hand). This
tool centralizes that and routes through the residential proxy (``YT_PROXY``) when
set, so YouTube's datacenter-IP blocks don't stop the download.

yt-dlp is imported lazily so importing this module never fails at boot.
"""

from __future__ import annotations

import glob
import os
import tempfile


def download_video(video_url: str, out_dir: str | None = None) -> str:
    """Download ``video_url`` to a local mp4 and return its path.

    Uses yt-dlp + the image's ffmpeg. Honours the ``YT_PROXY`` env var
    (``http://user:pass@host:port`` residential proxy) when set; YouTube blocks
    datacenter IPs, so on a VPS this is required for YouTube sources.
    """
    if not video_url:
        raise ValueError("video_url is required")

    import yt_dlp

    out_dir = out_dir or tempfile.mkdtemp(prefix="vod_")
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "%(id)s.%(ext)s")

    opts = {
        # Cap at 1080p: Nemotron analysis is <=1080p and clips are cropped from
        # this, so 4K just wastes (metered residential proxy) bandwidth + time.
        # Prefer a single mp4; fall back to bestvideo+bestaudio merged to mp4.
        "format": (
            "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
            "b[height<=1080][ext=mp4]/b[height<=1080]/b"
        ),
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
    }
    proxy = os.getenv("YT_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("ALL_PROXY")
    if proxy:
        opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video_url])

    produced = sorted(
        glob.glob(os.path.join(out_dir, "*.mp4"))
        or glob.glob(os.path.join(out_dir, "*"))
    )
    if not produced:
        raise RuntimeError(f"video download failed for {video_url}")
    return produced[0]
