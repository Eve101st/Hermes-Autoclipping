#!/usr/bin/env python3
"""Manual single-tool test harness — replaces the deleted `POST /tools/{name}` bridge.

Calls a pipeline tool directly, exactly as the MCP server (`mcp_server.py`) would,
so it is a faithful smoke test. Run it inside the project venv with the SAME env the
MCP server gets (the `mcp_servers.autoclipping.env:` block in Hermes' config.yaml —
FAL_KEY, BLOTATO_API_KEY, ...), or the tools that need those keys will fail the same
way they would under Hermes.

Usage:
    python scripts/call_tool.py <tool_name> ['<json-args>']

Examples:
    python scripts/call_tool.py get_transcript '{"video_url": "https://youtu.be/..."}'
    python scripts/call_tool.py cut_clips '{"video_url": "/path/v.mp4", "timestamps": [...]}'
    python scripts/call_tool.py cleanup_files
"""

import json
import sys

from tools import analyzer, cleanup, clipper, publisher, transcript

DISPATCH = {
    "get_transcript": transcript.get_transcript,
    "identify_moments": analyzer.identify_moments,
    "analyze_clips": analyzer.analyze_clips,
    "cut_clips": clipper.cut_clips,
    "publish_clips": publisher.publish_clips,
    "cleanup_files": cleanup.cleanup_files,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        print("tools:", ", ".join(DISPATCH))
        return 0 if len(argv) >= 2 else 2

    name = argv[1]
    if name not in DISPATCH:
        print(f"unknown tool {name!r}; choose from: {', '.join(DISPATCH)}", file=sys.stderr)
        return 2

    args = json.loads(argv[2]) if len(argv) > 2 else {}
    result = DISPATCH[name](**args)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
