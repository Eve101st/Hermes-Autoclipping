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
from tools.cleanup import cleanup_files as _cleanup_files
from tools.clipper import cut_clips as _cut_clips
from tools.publisher import publish_clips as _publish_clips
from tools.reframe import capture_frame as _capture_frame
from tools.reframe import qa_frames as _qa_frames
from tools.reframe import reframe_vertical as _reframe_vertical
from tools.transcript import get_transcript as _get_transcript

mcp = FastMCP("autoclipping")


@mcp.tool
def get_transcript(video_url: str) -> str:
    """Extract a timestamped plain-text transcript. `video_url` is EITHER a
    YouTube/Twitch URL OR a LOCAL file path (e.g. a Telegram-uploaded video at
    /var/lib/telegram-bot-api/<bot>/videos/...). For a local file it transcribes
    directly with whisper. Returns one segment per line, prefixed with [HH:MM:SS].
    """
    return _get_transcript(video_url)


@mcp.tool
def identify_moments(transcript: str) -> list[dict]:
    """From a timestamped transcript, return the TEN most clip-worthy windows
    (each <=2 min, on sentence boundaries) as a list of {start, end, reason}."""
    return _identify_moments(transcript)


@mcp.tool
def cut_clips(video_path: str, timestamps: list[dict]) -> list[str]:
    """Cut the given windows out of a LOCAL video file to 9:16 vertical mp4s in
    /tmp/clips, return paths. `video_path` is a Telegram-uploaded video file on
    disk (e.g. /var/lib/telegram-bot-api/<bot>/videos/...) — source videos are
    uploaded to the bot, NOT downloaded from a URL. Cut directly with ffmpeg;
    audio+video stay together."""
    return _cut_clips(video_path, timestamps)


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


@mcp.tool
def cleanup_files() -> dict:
    """Free disk: delete the stored uploaded videos/transcripts and generated
    clips (/tmp/clips + Hermes' upload cache + the Bot API server's downloads).
    Call this when the user asks to clean up / says /cleanup. Returns a summary
    {files_deleted, freed_mb, locations}."""
    return _cleanup_files()


@mcp.tool
def capture_frame(video_path: str, at_seconds: float = 0.0) -> str:
    """Grab ONE frame from a local video at `at_seconds` → a PNG path. Use it to
    PROBE a clip for the vision model (classify content / locate the facecam +
    gameplay + point-of-interest) before reframing, and for QA. Returns the PNG path."""
    return _capture_frame(video_path, at_seconds)


@mcp.tool
def reframe_vertical(src: str, out_path: str, layout: dict | None = None,
                     start: float | None = None, duration: float | None = None) -> str:
    """Render a LOCAL video to a 1080x1920 (9:16) mp4 per `layout`, optionally cutting
    [start, start+duration] first. Keeps gameplay AND facecam as moving video — use
    this instead of a blind center-crop for streamer content. `layout` = {"mode": ...}:
      center   — scale-to-cover + center-crop (may lose edges);
      fit_blur — whole frame fit to width over a blurred fill (nothing lost);
      crop     — crop {region:{x,y,w,h}} then cover to 9:16;
      split    — stack two regions (top/bottom {x,y,w,h}, optional top_h) e.g. gameplay
                 over facecam;
      overlay  — base region fills 9:16, cam region overlaid as PIP (base/cam {x,y,w,h},
                 optional pip_w/pos_x/pos_y).
    Regions are SOURCE pixel coords from the vision probe. Returns out_path."""
    return _reframe_vertical(src, out_path, layout, start, duration)


@mcp.tool
def qa_frames(clip_path: str) -> dict:
    """Capture the FIRST and LAST frame of a finished clip for a QA vision check
    (verify the reframe/crop is correct — facecam + gameplay visible, point-of-interest
    in frame, no stray bars). Returns {first, last, duration}."""
    return _qa_frames(clip_path)


if __name__ == "__main__":
    # Default transport is stdio — the form Hermes launches.
    mcp.run()
