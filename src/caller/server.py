"""FastAPI server: TwiML webhook + the media-stream websocket Twilio dials into.

Flow per call: the dialer creates an outbound call whose TwiML points here.
Twilio fetches /twiml (which names the scenario as a stream parameter), then
opens /ws and streams mulaw audio both ways. One websocket session == one
pipeline run == one artifact directory.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import quoteattr

from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse, Response
from loguru import logger

from caller.config import Config
from caller.pipeline import run_call_pipeline
from caller.scenario import load_scenario
from caller.store import create_call_dir, save_artifacts


def twiml_for_scenario(cfg: Config, scenario_id: str) -> str:
    ws_url = cfg.public_base_url.replace("https://", "wss://", 1) + "/ws"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url={quoteattr(ws_url)}>
      <Parameter name="scenario" value={quoteattr(scenario_id)} />
    </Stream>
  </Connect>
</Response>"""


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="pgai-caller")

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    # Twilio POSTs the webhook by default; GET kept for eyeball-debugging.
    @app.api_route("/twiml", methods=["GET", "POST"])
    async def twiml(scenario: str) -> Response:
        load_scenario(scenario)  # fail at webhook time, not mid-call
        return Response(content=twiml_for_scenario(cfg, scenario), media_type="application/xml")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()

        # Twilio's first two frames: "connected", then "start" with the sids
        # and our custom parameters.
        start_data = None
        for _ in range(2):
            msg = json.loads(await websocket.receive_text())
            if msg.get("event") == "start":
                start_data = msg["start"]
        if start_data is None:
            logger.error("websocket opened but no Twilio start message arrived")
            await websocket.close()
            return

        stream_sid = start_data["streamSid"]
        call_sid = start_data.get("callSid", "")
        scenario_id = start_data.get("customParameters", {}).get("scenario", "")
        scenario = load_scenario(scenario_id)
        logger.info(f"call {call_sid}: scenario '{scenario_id}' connected (stream {stream_sid})")

        call_dir = create_call_dir(scenario.id)
        result = None
        try:
            result = await run_call_pipeline(websocket, stream_sid, call_sid, scenario, cfg)
        finally:
            if result is not None:
                save_artifacts(
                    call_dir,
                    result.machine,
                    result.observer.call_start_ts,
                    meta={
                        "scenario": scenario.id,
                        "title": scenario.title,
                        "category": scenario.category,
                        "behavior": scenario.behavior,
                        "barge_in_policy": scenario.barge_in_policy.value,
                        "call_sid": call_sid,
                        "stream_sid": stream_sid,
                        "ended_by": result.ended_by,
                        "model": cfg.patient_model,
                    },
                )
                logger.info(f"call {call_sid}: artifacts saved to {call_dir}")
            else:
                (call_dir / "FAILED").write_text("pipeline crashed before completing; see logs\n")
                logger.error(f"call {call_sid}: pipeline failed, marker left in {call_dir}")

    @app.get("/")
    async def root() -> PlainTextResponse:
        return PlainTextResponse("pgai-caller: POST /twiml?scenario=<id>, WS /ws")

    return app
