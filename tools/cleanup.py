"""Cleanup — free the disk used by uploaded videos/transcripts and generated clips.

Public API:
    cleanup_files() -> dict

There is intentionally NO auto-clean: a job's source upload and output clips
persist after publishing (so the user can re-publish / re-cut) until they ask to
clean up. This deletes, across every place the pipeline accumulates files:
  - /tmp/clips                          (generated 9:16 clips)
  - /data/.hermes/cache/{videos,documents}  (Hermes' upload cache)
  - /var/lib/telegram-bot-api/*/{videos,documents,...}  (local Bot API downloads)

It removes the *contents* of those dirs, never the dirs themselves or any server
state, so the gateway / bot-api server keep working.
"""

from __future__ import annotations

import glob
import os
import shutil

_CLIP_DIR = "/tmp/clips"
_CACHE_DIRS = [
    "/data/.hermes/cache/videos",
    "/data/.hermes/cache/documents",
]
# Local Bot API server media dirs (bot id is dynamic -> glob it).
_BOTAPI_GLOBS = [
    "/var/lib/telegram-bot-api/*/videos",
    "/var/lib/telegram-bot-api/*/documents",
    "/var/lib/telegram-bot-api/*/music",
    "/var/lib/telegram-bot-api/*/animations",
    "/var/lib/telegram-bot-api/*/video_notes",
]


def _entry_size(path: str) -> int:
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _clear_dir(path: str) -> tuple[int, int]:
    """Delete the contents of `path` (not the dir). Returns (bytes_freed, count)."""
    if not os.path.isdir(path):
        return 0, 0
    freed = 0
    count = 0
    for entry in glob.glob(os.path.join(path, "*")):
        try:
            size = _entry_size(entry)
            if os.path.isdir(entry):
                shutil.rmtree(entry, ignore_errors=True)
            else:
                os.remove(entry)
            freed += size
            count += 1
        except OSError:
            pass
    return freed, count


def cleanup_files() -> dict:
    """Delete stored uploaded videos/transcripts and generated clips.

    Returns {files_deleted, freed_mb, locations:[{path, files, freed_bytes}]}.
    """
    targets = [_CLIP_DIR] + _CACHE_DIRS
    for pattern in _BOTAPI_GLOBS:
        targets.extend(glob.glob(pattern))

    locations = []
    total_freed = 0
    total_files = 0
    for path in targets:
        freed, count = _clear_dir(path)
        if count:
            locations.append({"path": path, "files": count, "freed_bytes": freed})
        total_freed += freed
        total_files += count

    return {
        "files_deleted": total_files,
        "freed_mb": round(total_freed / (1024 * 1024), 1),
        "locations": locations,
    }
