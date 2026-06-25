"""Individual tool modules invoked by the Hermes Agent pipeline.

Each module exposes one or more plain functions (no framework coupling) so they
can be called directly, via the `POST /tools/{name}` bridge in `app.py`, or wrapped
behind an MCP server for Hermes (see `tools_manifest.json` and the architecture
note in PROJECT_STATUS.md).

Functions:
    transcript.get_transcript(video_url)        -> str
    analyzer.identify_moments(transcript)       -> list[dict]
    analyzer.analyze_clips(clip_paths)          -> list[dict]
    clipper.cut_clips(video_path, timestamps)   -> list[str]
    publisher.publish_clips(clip_paths, captions) -> list[dict]
"""
