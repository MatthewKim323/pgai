# pgai-caller

An automated "patient" that phone-calls the Pretty Good AI test line
(+1-805-439-8008), holds a natural voice conversation with the agent,
records and transcribes both sides, and mines the transcripts for bugs.

Built for the Pretty Good AI engineering challenge. Design rationale lives in
[ARCHITECTURE.md](ARCHITECTURE.md); found issues live in [BUGS.md](BUGS.md).

```
Twilio outbound call ──websocket──▶ pipecat pipeline
    Deepgram nova-3 STT     hears the agent
    turn-state machine      turn-taking + barge-in (pure, unit-tested)
    Claude Haiku            plays a scripted patient persona
    ElevenLabs turbo TTS    speaks as the patient
Twilio dual-channel recording ──▶ mp3 (agent left, patient right)
```

## Setup

Requirements: Python 3.11+, [ffmpeg](https://ffmpeg.org) on PATH, and a tunnel
tool ([ngrok](https://ngrok.com) or cloudflared) so Twilio can reach the local
websocket server.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env                                    # fill in keys (below)
cp scenarios/identity.example.yaml scenarios/identity.local.yaml   # demo signup identity
```

Accounts / keys for `.env` (see `.env.example` for the full list):

| var | what |
|---|---|
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | telephony + call recording |
| `TWILIO_FROM_NUMBER` | the ONE number all test calls originate from |
| `DEEPGRAM_API_KEY` | streaming STT (agent's side of the call) |
| `ANTHROPIC_API_KEY` | the patient brain (Haiku) + the bug judge (Sonnet) |
| `ELEVENLABS_API_KEY` | the patient's voice |
| `PUBLIC_BASE_URL` | your tunnel's https URL |

`scenarios/identity.local.yaml` (gitignored) holds the identity registered
with the demo practice at pgai.us/athena, so existing-patient scenarios pass
name/DOB verification against a real record.

## Run

```bash
# terminal 1: expose the local server
ngrok http 8765          # put the https URL in PUBLIC_BASE_URL

# terminal 2: one command per test call
python -m caller call refill
```

`call` starts the server in-process if one isn't running, dials the test
line, runs the scenario, waits for hangup, downloads the dual-channel
recording, and prints a latency + transcript summary. Everything lands in
`calls/NN-<scenario>/`.

More:

```bash
python -m caller list                    # scenario library + completed calls
python -m caller campaign --all          # run every scenario back to back
python -m caller analyze                 # LLM judge -> findings.json + BUGS.md
python -m caller dashboard               # mission control at localhost:8090
pytest                                   # 70+ tests, no network needed
```

## Scenarios

Each call is a YAML file in `scenarios/`: who the patient is, how they talk
(`baseline`, `rambler`, `interrupter`, `confused`, `topic_switcher`), what
they want, and how the call should end. The library covers scheduling,
rescheduling/canceling, refills, hours/insurance questions, and deliberate
edge cases (Sunday-booking bait, barge-in stress with interruptions disabled
on our side, multi-thread topic switching, and safety-boundary probes).
Adding coverage means adding a YAML file, not touching code.

## Artifacts

```
calls/03-refill/
  meta.json         scenario, call sid, how the call ended
  transcript.txt    [mm:ss] AGENT/PATIENT lines (what BUGS.md cites)
  transcript.json   same, structured
  timeline.json     every turn-state event
  telemetry.json    our response latency + the agent's response gaps
  findings.json     the judge's findings for this call
  recording.mp3     both sides, dual-channel
```

## Repo map

```
src/caller/
  turnstate.py      pure turn-taking state machine (the core; heavily tested)
  scenario.py       YAML persona loader + system-prompt builder
  pipeline.py       pipecat pipeline: STT / LLM / TTS / turn strategies
  observer.py       pipecat frames -> turn-state signals
  server.py         FastAPI: TwiML webhook + Twilio media-stream websocket
  dialer.py         outbound calls, dial guard, recording download
  orchestrate.py    call lifecycle: dial -> wait -> correlate -> attach mp3
  transcript.py     event timeline -> two-party transcript
  telemetry.py      per-turn latency ledgers (ours vs. the agent's)
  analyze/          LLM judge + BUGS.md renderer
  dashboard.py      mission control UI
scenarios/          the test-call library (YAML)
tests/              everything above, no network required
```
