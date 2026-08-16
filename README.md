# pgai-caller

An automated "patient" that phone-calls the Pretty Good AI test line
(+1-805-439-8008), holds a natural voice conversation with the Athena agent,
records and transcribes both sides, and mines the transcripts for bugs.

Built for the Pretty Good AI engineering challenge.

## How it works (short version)

A Pipecat pipeline bridged to a live phone call over Twilio Media Streams:

```
Twilio outbound call ──websocket──▶ pipeline
    Deepgram nova-3 STT  (hears the agent)
    turn-state machine   (turn-taking + barge-in, pure & unit-tested)
    Claude Haiku         (plays a scripted patient persona)
    ElevenLabs turbo TTS (speaks as the patient)
Twilio dual-channel recording ──▶ mp3 with both sides
```

Every call runs a YAML-defined scenario (persona + goal + behavior profile) and
produces a full artifact set: aligned transcript, turn-state timeline, per-turn
latency telemetry, and audio. A judge pass over the artifacts drafts the bug
report. See `ARCHITECTURE.md` for the design rationale.

## Status

Under active development. Setup and run instructions land alongside the
first working call.
