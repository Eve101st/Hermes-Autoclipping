"""§4d — vertical reframe + layout composition + frame/QA capture.

Deterministic ffmpeg building blocks for the smart 9:16 reframe. The *intelligence*
(probe a frame → vision-classify content → pick a layout + regions → QA the result)
is orchestrated by the agent (Owl Alpha) using the vision model (§8). These functions
just execute a chosen layout, so they stay testable.

A blind center-crop butchers gameplay (facecam in a corner, action across the wide
frame). The layouts here keep BOTH gameplay and facecam as moving video.

Regions are dicts ``{"x","y","w","h"}`` in SOURCE pixel coordinates — the same space
as the frame the vision model looked at. All renders output 1080x1920 (9:16) mp4.
"""

from __future__ import annotations

import os
import subprocess

W, H = 1080, 1920  # target 9:16

_ENC = [
    "-c:v", "libx264", "-preset", "veryfast",
    "-c:a", "aac", "-movflags", "+faststart",
]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _r(region: dict, key: str) -> int:
    """Read an int pixel value from a region dict (raises if missing)."""
    if not region or key not in region:
        raise ValueError(f"layout region is missing '{key}' (need x,y,w,h)")
    return int(region[key])


def capture_frame(video_path: str, at_seconds: float = 0.0, out_path: str | None = None) -> str:
    """Grab a single frame from ``video_path`` at ``at_seconds`` to a PNG; return its path.

    Used to PROBE a clip for the vision model (§8) and for the QA pass. ``video_path``
    is a local file. Pick a representative instant (start of the clip works well).
    """
    if not os.path.isfile(video_path):
        raise ValueError(f"video_path must be a local file; got {video_path!r}")
    out_path = out_path or os.path.join(
        "/tmp/frames", f"frame_{int(max(0.0, at_seconds) * 1000):09d}.png"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    _run(["ffmpeg", "-y", "-ss", f"{max(0.0, at_seconds):.3f}", "-i", video_path,
          "-frames:v", "1", "-q:v", "2", out_path])
    return out_path


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def qa_frames(clip_path: str) -> dict:
    """Capture the FIRST and LAST frame of a finished clip for a QA vision check.

    Feed both to the vision model (§8) to verify the reframe/crop is correct
    (facecam visible, gameplay visible, point-of-interest in frame, no stray bars).
    Returns ``{"first": <png>, "last": <png>, "duration": <seconds>}``.
    """
    if not os.path.isfile(clip_path):
        raise ValueError(f"clip_path must be a local file; got {clip_path!r}")
    dur = _duration(clip_path)
    return {
        "first": capture_frame(clip_path, 0.0, "/tmp/frames/qa_first.png"),
        "last": capture_frame(clip_path, max(0.0, dur - 0.1), "/tmp/frames/qa_last.png"),
        "duration": dur,
    }


def _cover(label_in: str, label_out: str, w: int = W, h: int = H) -> str:
    """scale-to-cover then center-crop a stream to exactly w x h."""
    return (f"[{label_in}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}[{label_out}]")


def _build_filtergraph(layout: dict) -> str:
    """Return an ffmpeg ``-filter_complex`` graph producing a final ``[out]`` (1080x1920).

    layout = {"mode": ..., ...}:
      center  : scale-to-cover + center-crop (legacy; may lose edges).
      fit_blur: whole frame fit to width over a blurred fill — nothing lost.
      crop    : crop {region} then cover-crop to 9:16. region={x,y,w,h}.
      split   : stack two regions to fill 9:16 (e.g. gameplay over facecam).
                top/bottom={x,y,w,h}; optional top_h (default 1280).
      overlay : base region fills 9:16; cam region overlaid as PIP.
                base/cam={x,y,w,h}; optional pip_w (default 410), pos x/y.
    """
    mode = (layout or {}).get("mode", "center")

    if mode == "center":
        return _cover("0:v", "out")

    if mode == "fit_blur":
        sigma = int(layout.get("blur", 20))
        return (
            "[0:v]split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma={sigma}[bgb];"
            f"[fg]scale={W}:-2[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[out]"
        )

    if mode == "crop":
        reg = layout.get("region") or layout
        x, y, w, h = (_r(reg, "x"), _r(reg, "y"), _r(reg, "w"), _r(reg, "h"))
        return (f"[0:v]crop={w}:{h}:{x}:{y},"
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[out]")

    if mode == "split":
        top, bot = layout.get("top"), layout.get("bottom")
        th_px = int(layout.get("top_h", 1280))
        bh_px = H - th_px
        tx, ty, tw, twh = (_r(top, "x"), _r(top, "y"), _r(top, "w"), _r(top, "h"))
        bx, by, bw, bwh = (_r(bot, "x"), _r(bot, "y"), _r(bot, "w"), _r(bot, "h"))
        return (
            f"[0:v]crop={tw}:{twh}:{tx}:{ty},"
            f"scale={W}:{th_px}:force_original_aspect_ratio=increase,crop={W}:{th_px}[top];"
            f"[0:v]crop={bw}:{bwh}:{bx}:{by},"
            f"scale={W}:{bh_px}:force_original_aspect_ratio=increase,crop={W}:{bh_px}[bot];"
            "[top][bot]vstack[out]"
        )

    if mode == "overlay":
        base, cam = layout.get("base"), layout.get("cam")
        pip_w = int(layout.get("pip_w", 410))
        px, py = int(layout.get("pos_x", W - pip_w - 24)), int(layout.get("pos_y", 24))
        bx, by, bw, bh = (_r(base, "x"), _r(base, "y"), _r(base, "w"), _r(base, "h"))
        cx, cy, cw, ch = (_r(cam, "x"), _r(cam, "y"), _r(cam, "w"), _r(cam, "h"))
        return (
            "[0:v]split=2[b][c];"
            f"[b]crop={bw}:{bh}:{bx}:{by},"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[base];"
            f"[c]crop={cw}:{ch}:{cx}:{cy},scale={pip_w}:-2[cam];"
            f"[base][cam]overlay={px}:{py}[out]"
        )

    raise ValueError(f"unknown reframe mode {mode!r} "
                     "(center|fit_blur|crop|split|overlay)")


def reframe_vertical(
    src: str,
    out_path: str,
    layout: dict | None = None,
    start: float | None = None,
    duration: float | None = None,
) -> str:
    """Render ``src`` to a 1080x1920 mp4 at ``out_path`` using ``layout`` (see
    ``_build_filtergraph``). If ``start``/``duration`` are given, cut that window
    first (so this can cut + compose in one pass). Returns ``out_path``.

    Both gameplay and facecam stay moving video. Defaults to a center-crop when no
    layout is given. Use ``fit_blur`` when nothing should be lost, or ``split`` /
    ``overlay`` with vision-supplied regions for gameplay+facecam composition.
    """
    if not os.path.isfile(src):
        raise ValueError(f"src must be a local video file; got {src!r}")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    graph = _build_filtergraph(layout or {"mode": "center"})

    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    cmd += ["-i", src]
    if duration is not None:
        cmd += ["-t", f"{max(0.0, duration):.3f}"]
    cmd += ["-filter_complex", graph, "-map", "[out]", "-map", "0:a?", *_ENC, out_path]
    _run(cmd)
    return out_path
