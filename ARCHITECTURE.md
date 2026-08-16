# Architecture

## How it works

One test call is one pipeline run. The CLI validates the scenario, places an
outbound Twilio call to the test line with dual-channel recording enabled, and
Twilio connects a Media Streams websocket back to our FastAPI server (through
an ngrok tunnel), carrying the scenario id as a stream parameter. That
websocket feeds a [Pipecat](https://github.com/pipecat-ai/pipecat) pipeline:
Deepgram nova-3 transcribes the agent's speech as it streams in, a
Claude Haiku "patient" — prompted from a YAML persona with a goal, a behavior
profile, and strict phone-voice discipline — decides what to say, and
ElevenLabs turbo speaks it back into the call. End-of-turn detection is
semantic (Pipecat's local smart-turn model over Silero VAD) rather than a
fixed silence gap, which is most of why the bot doesn't leave dead air or
talk over the agent's pauses. A pure, I/O-free turn-state machine observes
the whole exchange; the transcript, the turn-state timeline, and the latency
telemetry are all projections of its single event record, so the artifacts
can never disagree with each other. After hangup, an LLM judge (Sonnet) reads
each transcript against the scenario's intent and the measured response gaps
and files findings with verbatim quotes; a merge pass dedups findings across
calls into `BUGS.md`.

## Why these choices

**Cascaded pipeline over a speech-to-speech Realtime API.** A realtime
speech-to-speech model would be less code, but this task is a *test harness*:
we need a text transcript of both sides as a first-class artifact, per-turn
latency measurements, scripted control over turn-taking (including
deliberately rude interruptions with our own barge-in disabled), and a cheap,
swappable persona brain. A cascaded STT→LLM→TTS pipeline gives all of that
for free, and closes the latency gap with streaming everything plus semantic
endpointing — the patient typically starts speaking well under a second after
the agent stops. **Pipecat over LiveKit Agents:** both stream well; Pipecat
speaks Twilio Media Streams natively over a plain websocket, so there's no
SIP trunk or media room between us and the phone call, and its turn-strategy
API let us flip interruption behavior per scenario. **Dual-channel Twilio
recording** (agent left, patient right) means the deliverable audio is
telephony ground truth rather than something we mix ourselves. **The pure
state machine** is the piece that makes the rest honest: turn-taking policy
is unit-tested without a phone call, and "our response latency" vs. "the
agent's response gaps" come from the same clock, so the telemetry that tunes
our bot is also admissible evidence in the bug report.
