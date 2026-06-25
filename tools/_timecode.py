"""Shared timecode helpers used by transcript / clipper / analyzer."""

from __future__ import annotations


def to_seconds(value) -> float:
    """Coerce a timestamp into seconds.

    Accepts a number (already seconds) or a "HH:MM:SS", "MM:SS", or "SS" string.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    parts = text.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_timestamp(seconds: float) -> str:
    """Render seconds as a zero-padded ``HH:MM:SS`` string."""
    seconds = int(round(float(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
