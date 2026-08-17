"""Call orchestration: everything between 'run this scenario' and a full
artifact directory.

The websocket session (server.py) owns the call's artifacts; the orchestrator
owns the call's lifecycle. They meet on the call SID: the dialer creates the
call, the server stamps the SID into meta.json when it saves, and the
orchestrator correlates the two to attach the recording.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from loguru import logger

from caller import store
from caller.config import Config
from caller.dialer import fetch_recording, place_call, wait_for_completion
from caller.server import create_app


def server_is_up(cfg: Config) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{cfg.port}/health", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def start_server_thread(cfg: Config) -> uvicorn.Server:
    """Run the FastAPI app in a daemon thread; returns once it accepts connections."""
    server = uvicorn.Server(
        uvicorn.Config(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True, name="caller-server").start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", cfg.port), timeout=0.5):
                return server
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"server did not come up on port {cfg.port}")


def find_call_dir(call_sid: str, calls_dir: Path = store.CALLS_DIR,
                  timeout_secs: float = 90.0) -> Path | None:
    """Locate the artifact dir the websocket session wrote for this call.

    Artifacts land when the pipeline finishes, which can lag the telephony
    hangup by a moment -- hence the short poll.
    """
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        for call_dir in reversed(store.list_calls(calls_dir)):
            meta_file = call_dir / "meta.json"
            if meta_file.exists() and json.loads(meta_file.read_text()).get("call_sid") == call_sid:
                return call_dir
        time.sleep(1.0)
    return None


def run_scenario(cfg: Config, scenario_id: str) -> Path | None:
    """Place one call and see it through to a complete artifact directory."""
    call_sid = place_call(cfg, scenario_id)
    status = wait_for_completion(cfg, call_sid)
    logger.info(f"call {call_sid}: telephony status '{status}'")

    call_dir = find_call_dir(call_sid)
    if call_dir is None:
        logger.error(
            f"call {call_sid}: no artifact dir appeared. Did Twilio reach "
            f"{cfg.public_base_url}? Check the tunnel and server logs."
        )
        return None

    fetch_recording(cfg, call_sid, call_dir)
    _print_summary(call_dir)
    return call_dir


def _print_summary(call_dir: Path) -> None:
    data = store.load_call(call_dir)
    tel = data.get("telemetry") or {}
    patient = (tel.get("patient") or {}).get("response_latency") or {}
    agent = (tel.get("agent_under_test") or {}).get("response_gap") or {}
    print(f"\n=== {call_dir.name} ===")
    print(f"duration: {tel.get('call_duration_secs', '?')}s, turns: {tel.get('completed_turns')}")
    if patient:
        print(f"our response latency: p50 {patient['p50']}s / max {patient['max']}s")
    if agent:
        print(f"agent response gap:  p50 {agent['p50']}s / max {agent['max']}s")
    print(f"transcript: {call_dir / 'transcript.txt'}")
    print(data["transcript_text"][:400] + ("..." if len(data["transcript_text"]) > 400 else ""))
