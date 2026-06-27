import shutil

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Autoclipping")


@app.get("/")
def root():
    """Health check. Probes for the `hermes` binary rather than hardcoding it.
    On the VPS Hermes is baked into the image (seeded into the /data volume), so it
    is normally present immediately; the probe still degrades gracefully if not."""
    hermes = "installed" if shutil.which("hermes") else "installing"
    return {"status": "Autoclipping pipeline is live", "hermes": hermes}


# --------------------------------------------------------------------------- #
# Tool bridge — POST /tools/{tool_name} with a JSON body of the tool's inputs.
#
# Lets each tool be exercised individually (e.g. via curl) and gives an MCP
# wrapper a single, uniform call surface. Tool functions are imported lazily so a
# missing heavy dependency (faster-whisper, etc.) never takes down the health
# check; the import error surfaces only when that specific tool is called.
# --------------------------------------------------------------------------- #
def _dispatch(tool_name: str):
    if tool_name == "get_transcript":
        from tools.transcript import get_transcript
        return get_transcript
    if tool_name == "identify_moments":
        from tools.analyzer import identify_moments
        return identify_moments
    if tool_name == "analyze_clips":
        from tools.analyzer import analyze_clips
        return analyze_clips
    if tool_name == "cut_clips":
        from tools.clipper import cut_clips
        return cut_clips
    if tool_name == "publish_clips":
        from tools.publisher import publish_clips
        return publish_clips
    return None


@app.post("/tools/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    func = _dispatch(tool_name)
    if func is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")

    try:
        body = await request.json() if await request.body() else {}
    except Exception:
        raise HTTPException(status_code=400, detail="request body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    try:
        result = func(**body)
    except TypeError as exc:  # wrong/missing arguments for the tool
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # tool-internal failure
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

    return {"tool": tool_name, "result": result}
