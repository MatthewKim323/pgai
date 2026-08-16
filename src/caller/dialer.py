"""Outbound dialing + recording retrieval via the Twilio REST API.

The dial guard is deliberate: this project may only ever call the Pretty Good
AI assessment line, so the guard lives here (the last hop before Twilio), not
just in documentation.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
from loguru import logger
from twilio.rest import Client

from caller.config import Config, assert_target_allowed


def twilio_client(cfg: Config) -> Client:
    return Client(cfg.twilio_account_sid, cfg.twilio_auth_token)


def place_call(cfg: Config, scenario_id: str, client: Client | None = None) -> str:
    """Start an outbound, dual-channel-recorded call. Returns the call SID."""
    assert_target_allowed(cfg.target_number)
    client = client or twilio_client(cfg)
    call = client.calls.create(
        to=cfg.target_number,
        from_=cfg.twilio_from_number,
        url=f"{cfg.public_base_url}/twiml?scenario={scenario_id}",
        record=True,
        recording_channels="dual",  # left: the agent under test, right: our patient
        time_limit=600,
    )
    logger.info(f"dialing {cfg.target_number} from {cfg.twilio_from_number}: call {call.sid}")
    return call.sid


def wait_for_completion(cfg: Config, call_sid: str, client: Client | None = None,
                        timeout_secs: float = 600.0) -> str:
    """Block until the call leaves any live state; returns the final status."""
    client = client or twilio_client(cfg)
    live = {"queued", "ringing", "in-progress"}
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        status = client.calls(call_sid).fetch().status
        if status not in live:
            return status
        time.sleep(2.0)
    return "timeout"


def fetch_recording(cfg: Config, call_sid: str, call_dir: Path,
                    client: Client | None = None, timeout_secs: float = 120.0) -> Path | None:
    """Download the call's dual-channel recording and convert it to mp3.

    Twilio finalizes recordings shortly after hangup, so this polls briefly.
    Returns the mp3 path, or None if no recording appeared in time.
    """
    client = client or twilio_client(cfg)
    deadline = time.monotonic() + timeout_secs
    recording = None
    while time.monotonic() < deadline:
        recordings = client.recordings.list(call_sid=call_sid, limit=5)
        done = [r for r in recordings if r.status == "completed"]
        if done:
            recording = done[0]
            break
        time.sleep(3.0)
    if recording is None:
        logger.warning(f"call {call_sid}: no completed recording within {timeout_secs}s")
        return None

    # RecordingChannels=2 in the media request keeps the stereo split.
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{cfg.twilio_account_sid}"
        f"/Recordings/{recording.sid}.wav?RequestedChannels=2"
    )
    wav_path = call_dir / "recording.wav"
    with httpx.stream(
        "GET", url, auth=(cfg.twilio_account_sid, cfg.twilio_auth_token), timeout=60.0
    ) as resp:
        resp.raise_for_status()
        with open(wav_path, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)

    mp3_path = call_dir / "recording.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path), "-b:a", "96k", str(mp3_path)],
        check=True,
    )
    wav_path.unlink()  # keep only the deliverable format
    logger.info(f"call {call_sid}: recording saved to {mp3_path}")
    return mp3_path
