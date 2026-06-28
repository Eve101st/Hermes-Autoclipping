"""Step 1 — transcript extraction.

Public API:
    get_transcript(video_url) -> str

Returns plain text, one segment per line, each prefixed with an ``[HH:MM:SS]``
timestamp:

    [00:00:03] welcome back to the stream
    [00:00:06] today we are looking at ...

Resolution order:
    1. YouTube  -> youtube-transcript-api (official captions), paced ~1s/request.
    2. Twitch   -> yt-dlp subtitle extraction (Twitch VODs rarely carry captions).
    3. Fallback -> faster-whisper (CPU) over audio pulled with yt-dlp + the
                   ffmpeg already present in the image.

The heavy/optional imports (yt-dlp, faster-whisper) are done lazily so importing
this module never fails just because a dependency is missing at boot.
"""

from __future__ import annotations

import glob
import os
import re
import tempfile
import time

from ._timecode import format_timestamp

# Pacing between successive caption requests, per the spec (be polite to the API).
_REQUEST_DELAY_SECONDS = 1.0

# Whisper model size for the CPU fallback. "base" is a reasonable speed/accuracy
# trade-off on CPU; bump to "small"/"medium" if transcription quality matters more
# than latency.
_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")


def _proxy_url() -> str | None:
    """Proxy for YouTube traffic, or None. Read at call time.

    Primary: the residential ``YT_PROXY`` (Smartproxy). Fallback: ``TOR_PROXY``
    (the in-container Tor SOCKS5, socks5://127.0.0.1:9050). A DEDICATED var — not
    the standard HTTPS_PROXY/ALL_PROXY — so it only affects the YouTube tools
    (yt-dlp / youtube-transcript-api), never fal / Blotato / Telegram, which must
    stay direct (Tor is slow / often blocked by them).
    """
    return os.getenv("YT_PROXY") or os.getenv("TOR_PROXY") or None


def _ydl_proxy_opts() -> dict:
    """yt-dlp options carrying the proxy, if configured (else empty)."""
    proxy = _proxy_url()
    return {"proxy": proxy} if proxy else {}


def get_transcript(video_url: str) -> str:
    """Return a timestamped plain-text transcript for ``video_url``."""
    if not video_url:
        raise ValueError("video_url is required")

    # Local file (e.g. a Telegram-uploaded video): transcribe it directly with
    # whisper — no captions API, no yt-dlp, no proxy.
    if os.path.isfile(video_url):
        return _render(_whisper_file(video_url))

    platform = _detect_platform(video_url)

    if platform == "youtube":
        segments = _youtube_captions(video_url)
        if segments:
            return _render(segments)

    if platform == "twitch":
        segments = _twitch_captions(video_url)
        if segments:
            return _render(segments)

    # No captions available (or an unknown host): transcribe the audio.
    segments = _whisper_fallback(video_url)
    return _render(segments)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _detect_platform(url: str) -> str:
    host = url.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "twitch.tv" in host:
        return "twitch"
    return "unknown"


def _render(segments: list[dict]) -> str:
    """segments: list of {"start": float_seconds, "text": str} -> plain text."""
    lines = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{format_timestamp(seg['start'])}] {text}")
    return "\n".join(lines)


def _youtube_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _youtube_captions(url: str) -> list[dict]:
    """Fetch official YouTube captions; return [] if none are available."""
    video_id = _youtube_video_id(url)
    if not video_id:
        return []

    time.sleep(_REQUEST_DELAY_SECONDS)  # ~1s pacing between requests
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        proxy = _proxy_url()
        if proxy:
            from youtube_transcript_api.proxies import GenericProxyConfig

            api = YouTubeTranscriptApi(
                proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy)
            )
        else:
            api = YouTubeTranscriptApi()

        raw = api.fetch(video_id).to_raw_data()  # [{text, start, duration}, ...]
    except Exception:
        # No transcript, transcripts disabled, region/IP block, etc. -> fall back.
        return []

    return [{"start": item["start"], "text": item["text"]} for item in raw]


def _twitch_captions(url: str) -> list[dict]:
    """Attempt Twitch caption extraction via yt-dlp; return [] if none."""
    try:
        import yt_dlp
    except Exception:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "%(id)s")
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
            "subtitleslangs": ["en", "en-US"],
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            **_ydl_proxy_opts(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception:
            return []

        vtts = glob.glob(os.path.join(tmp, "*.vtt"))
        if not vtts:
            return []
        return _parse_vtt(vtts[0])


def _parse_vtt(path: str) -> list[dict]:
    """Minimal WebVTT parser -> [{"start": seconds, "text": str}]."""
    segments: list[dict] = []
    cue_start: float | None = None
    cue_text: list[str] = []

    timing = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    )

    def flush():
        if cue_start is not None and cue_text:
            segments.append({"start": cue_start, "text": " ".join(cue_text)})

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []

    for line in lines:
        match = timing.search(line)
        if match:
            flush()
            cue_start = _vtt_time_to_seconds(match.group(1))
            cue_text = []
        elif line.strip() and not line.strip().isdigit() and line.strip() != "WEBVTT":
            # Strip inline tags like <c> and timestamps inside the cue.
            cue_text.append(re.sub(r"<[^>]+>", "", line).strip())
    flush()
    return segments


def _vtt_time_to_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def _whisper_file(path: str) -> list[dict]:
    """Transcribe a local media file directly with faster-whisper.

    faster-whisper decodes the file's own audio stream (works on mp4/mov/etc.),
    so no separate ffmpeg extraction or yt-dlp download is needed.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path)
    return [{"start": seg.start, "text": seg.text} for seg in segments]


def _whisper_fallback(url: str) -> list[dict]:
    """Download audio with yt-dlp and transcribe on CPU with faster-whisper."""
    audio_path = _download_audio(url)
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_path)
        return [{"start": seg.start, "text": seg.text} for seg in segments]
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def _download_audio(url: str) -> str:
    """Pull audio to a temp wav via yt-dlp (uses the image's ffmpeg)."""
    import yt_dlp

    tmp_dir = tempfile.mkdtemp()
    outtmpl = os.path.join(tmp_dir, "audio.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        **_ydl_proxy_opts(),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    produced = glob.glob(os.path.join(tmp_dir, "audio.*"))
    if not produced:
        raise RuntimeError(f"audio download failed for {url}")
    return produced[0]
