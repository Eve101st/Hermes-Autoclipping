"""Individual tool modules invoked by the Hermes Agent pipeline.

Each module exposes one or more plain functions (no framework coupling) so they
can be called directly, wrapped behind the MCP server Hermes calls
(`mcp_server.py`), or exercised manually via `scripts/call_tool.py`.

Functions:
    transcript.get_transcript(video_url)        -> str
    analyzer.identify_moments(transcript)       -> list[dict]
    analyzer.analyze_clips(clip_paths)          -> list[dict]
    clipper.cut_clips(video_path, timestamps)   -> list[str]
    publisher.publish_clips(clip_paths, captions) -> list[dict]
    cleanup.cleanup_files()                     -> dict
"""
