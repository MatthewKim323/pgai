"""Mission control: a local dashboard over the call artifacts.

Zero build step, zero external assets: one FastAPI app serving one inlined
HTML page plus a JSON API over `calls/`. Run with `python -m caller dashboard`
and open http://localhost:8090.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from caller import store

STATIC_DIR = Path(__file__).parent / "static"


def create_dashboard_app(calls_dir: Path = store.CALLS_DIR) -> FastAPI:
    app = FastAPI(title="pgai-caller mission control")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (STATIC_DIR / "dashboard.html").read_text()

    @app.get("/api/calls")
    async def calls() -> list:
        out = []
        for call_dir in store.list_calls(calls_dir):
            data = store.load_call(call_dir)
            findings_file = call_dir / "findings.json"
            data["findings"] = (
                json.loads(findings_file.read_text()) if findings_file.exists() else None
            )
            out.append(data)
        return out

    @app.get("/api/calls/{call_id}/recording.mp3")
    async def recording(call_id: str) -> FileResponse:
        path = (calls_dir / call_id / "recording.mp3").resolve()
        # call_id comes from a URL: never let it walk out of the calls dir
        if calls_dir.resolve() not in path.parents or not path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="audio/mpeg")

    return app
