"""MCP server exposing the Autoclipping pipeline tools to Hermes Agent.

Hermes registers and calls tools over **MCP**, not over a plain REST manifest, so
this module wraps the five pipeline functions as MCP tools. Hermes spawns it as a
**stdio** subprocess once it is registered in `$HERMES_HOME/config.yaml`:

    mcp_servers:
      autoclipping:
        command: /usr/local/bin/python
        args: ["/app/mcp_server.py"]
        enabled: true
        tools:
          include: [get_transcript, identify_moments, cut_clips,
                    analyze_clips, publish_clips]

The subprocess inherits the container env (compose env_file: FAL_KEY,
BLOTATO_API_KEY, …), which `config.py` reads. The FastAPI `POST /tools/{name}` bridge in `app.py`
remains for manual `curl` testing; this server is the path Hermes actually uses.
"""

from __future__ import annotations

from fastmcp import FastMCP

from tools.analyzer import analyze_clips as _analyze_clips
from tools.analyzer import identify_moments as _identify_moments
from tools.clipper import cut_clips as _cut_clips
from tools.publisher import publish_clips as _publish_clips
from tools.transcript import get_transcript as _get_transcript

mcp = FastMCP("autoclipping")


@mcp.tool
def get_transcript(video_url: str) -> str:
    """Extract a timestamped plain-text transcript for a YouTube or Twitch video.

    Returns one segment per line, each prefixed with [HH:MM:SS]. Uses captions
    when available, else falls back to faster-whisper on the audio.
    """
    return _get_transcript(video_url)


@mcp.tool
def identify_moments(transcript: str) -> list[dict]:
    """From a timestamped transcript, return the TEN most clip-worthy windows
    (each <=2 min, on sentence boundaries) as a list of {start, end, reason}."""
    return _identify_moments(transcript)


@mcp.tool
def cut_clips(video_url: str, timestamps: list[dict]) -> list[str]:
    """Download ONLY the needed segments from the source VOD (via yt-dlp
    --download-sections), cut each to 9:16 vertical, write to /tmp/clips,
    and return the output file paths. Audio+video stay together."""
    return _cut_clips(video_url, timestamps)


@mcp.tool
def analyze_clips(clip_paths: list[str]) -> list[dict]:
    """For each rendered clip, return the best 30-90s moment, a caption, and a
    virality score: {clip, start, end, caption, virality_score}."""
    return _analyze_clips(clip_paths)


@mcp.tool
def publish_clips(clip_paths: list[str], captions: list[str]) -> list[dict]:
    """Upload each clip to Blotato and create a post per configured target
    (useNextFreeSlot). Returns one result per clip/target."""
    return _publish_clips(clip_paths, captions)


if __name__ == "__main__":
    # Default transport is stdio — the form Hermes launches.
    mcp.run()
