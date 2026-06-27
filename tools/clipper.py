"""Step 3 — cut clips and convert to 9:16 vertical.

Public API:
    cut_clips(video_url, timestamps) -> list[str]

``timestamps`` is a list of dicts with ``start`` and ``end`` (each either seconds
or an "HH:MM:SS"/"MM:SS" string); extra keys such as ``reason``/``caption`` are
ignored.

Uses yt-dlp's ``--download-sections`` to fetch ONLY the segments we need from
the source VOD — a 2-hour VOD where we want 10 ~90s clips downloads ~15 min of
footage instead of the full 2h, sidestepping YouTube's datacenter-IP throttling.
Each segment is re-encoded and center-cropped to 1080x1920 (9:16) and written to
``/tmp/clips``. Returns the list of output paths.

yt-dlp is imported lazily so importing this module never fails at boot.
"""

from __future__ import annotations

import glob
import os
import subprocess
import tempfile

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


def _proxy() -> str | None:
    """Proxy URL for yt-dlp (Tor SOCKS5 on the VPS, residential elsewhere)."""
    return os.getenv("YT_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("ALL_PROXY") or None


def cut_clips(video_url: str, timestamps: list[dict]) -> list[str]:
    """Download only the needed segments from ``video_url`` and cut to 9:16 mp4s.

    Each timestamp dict has ``start``/``end`` (seconds or HH:MM:SS). Returns a
    list of output clip paths in /tmp/clips. Audio+video stay together — the
    downloaded mp4 has both tracks; ffmpeg crops the segment as-is.
    """
    if not video_url:
        raise ValueError("video_url is required")
    if not timestamps:
        return []

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Build the section list for yt-dlp. Each window becomes a section; we pad
    # the start by LEAD_BUFFER_SECONDS (clamped at 0) so the downloaded segment
    # already includes the buffer — ffmpeg just needs to crop, not re-seek.
    sections: list[tuple[float, float]] = []
    for window in timestamps:
        start = to_seconds(window.get("start", 0))
        end = to_seconds(window.get("end", 0))
        if end - start <= 0:
            continue
        buffered_start = max(0.0, start - LEAD_BUFFER_SECONDS)
        sections.append((buffered_start, end))
    if not sections:
        return []

    with tempfile.TemporaryDirectory(prefix="vod_dl_") as tmp:
        outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")

        # Merge overlapping/adjacent sections so yt-dlp makes fewer connections.
        merged = _merge_sections(sections)

        section_arg = ",".join(
            f"{s:.3f}-{e:.3f}" for s, e in merged
        )

        import yt_dlp

        opts = {
            # Cap at 1080p: Nemotron analysis is <=1080p and clips are cropped from
            # this, so 4K just wastes bandwidth + time.
            "format": (
                "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
                "b[height<=1080][ext=mp4]/b[height<=1080]/b"
            ),
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "download_sections": [f"*{section_arg}"],
        }
        proxy = _proxy()
        if proxy:
            opts["proxy"] = proxy

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video_url])

        # yt-dlp with --download-sections writes one file per section, named with
        # a section index by default. We glob everything we got, then map back to
        # output clip paths in order.
        downloaded = sorted(
            glob.glob(os.path.join(tmp, "*.mp4"))
            or glob.glob(os.path.join(tmp, "*"))
        )
        if not downloaded:
            raise RuntimeError(f"segment download failed for {video_url}")

        # If yt-dlp produced one merged file (single section), use it; otherwise
        # we have one file per section. Either way, we now cut each segment out
        # of the appropriate source file with ffmpeg.
        outputs: list[str] = []
        for index, (start, end) in enumerate(sections):
            # Find the source file that covers this section. With merged sections
            # yt-dlp may have produced fewer files than timestamps; map by checking
            # which downloaded file's section range covers this start.
            src = _find_source(downloaded, start, merged, tmp)
            duration = end - start

            out_path = os.path.join(OUTPUT_DIR, f"clip_{index:03d}.mp4")
            cmd = [
                "ffmpeg",
                "-y",
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
            outputs.append(out_path)

    return outputs


def _merge_sections(sections: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping/adjacent sections to reduce yt-dlp connections."""
    if not sections:
        return []
    sorted_sections = sorted(sections)
    merged: list[tuple[float, float]] = [sorted_sections[0]]
    for s, e in sorted_sections[1:]:
        prev_s, prev_e = merged[-1]
        if s <= prev_e + 1.0:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))
    return merged


def _find_source(
    downloaded: list[str],
    section_start: float,
    merged: list[tuple[float, float]],
    tmp: str,
) -> str:
    """Pick the downloaded file that covers ``section_start``.

    yt-dlp with --download-sections writes files named like
    ``<id> [section].ext`` or ``<id>.ext``. When sections were merged, one file
    covers multiple windows. We map by checking which merged range contains the
    start; if that's ambiguous, fall back to the single-file case.
    """
    if len(downloaded) == 1:
        return downloaded[0]

    # yt-dlp names section files as "<id> [1234.567-789.012].mp4" when multiple
    # sections are requested. Try to match by parsing the section range from the
    # filename; otherwise, pick the file whose merged range covers this start.
    for path in downloaded:
        base = os.path.basename(path)
        # yt-dlp section format: " [start-end]" before the extension.
        bracket = base.rfind(" [")
        if bracket != -1 and base.endswith("]"):
            range_part = base[bracket + 2:-1]
            parts = range_part.split("-")
            if len(parts) == 2:
                try:
                    s, e = float(parts[0]), float(parts[1])
                    if s <= section_start < e:
                        return path
                except ValueError:
                    pass

    # Fallback: use the merged range index to pick the right file.
    for i, (s, e) in enumerate(merged):
        if s <= section_start < e and i < len(downloaded):
            return downloaded[i]

    return downloaded[0]
