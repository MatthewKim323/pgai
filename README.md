# pgai-caller

An automated "patient" that phone-calls the Pretty Good AI test line
(+1-805-439-8008), holds a natural voice conversation with the agent,
records and transcribes both sides, and mines the transcripts for bugs.

## Results

| | |
|---|---|
| Calls completed | **15**, each 1:40-4:45, every one a full conversation with a natural ending |
| Bugs found | **14 confirmed (6 high)** + 4 pending audio verification -- [BUGS.md](BUGS.md) |
| Flagships | transfers route to a dead-end line that hangs up (reproduced 3x); the practice is in Nashville in call 04 and at an Austin address in call 06 |
| Our response latency | ~1.1s median, worst turn 1.6s after tuning -- [docs/LATENCY.md](docs/LATENCY.md) |
| Audio quality | double-talk ≤2.3% on all 15 recordings, dead air attributable to the agent under test -- [docs/AUDIOQA.md](docs/AUDIOQA.md) |
| Campaign cost | ≈$3.50 total ($0.12 call time + $1.15 number + ~$2 LLM; Deepgram fit in free credit) |

**Reviewing this?** Fastest path: listen to `calls/14-hunt-1/recording.mp3`
(a call whose persona the harness authored itself), then
`calls/11-edge-topic-switcher/recording.mp3` at 1:29 (the flagship dead-end
transfer, over the caller's objection), then read [BUGS.md](BUGS.md). Design
rationale is in [ARCHITECTURE.md](ARCHITECTURE.md); the improvement arc,
call by call, is in [docs/ITERATION.md](docs/ITERATION.md).

## How it works

```
Twilio outbound call ──websocket──▶ pipecat pipeline
    Deepgram nova-3 STT       hears the agent
    speculative generation    reply stream opens BEFORE the turn ends
    turn-state machine        turn-taking + barge-in (pure, unit-tested)
    Claude Haiku              plays a scripted patient persona
    Deepgram Aura-2 TTS       speaks as the patient (distinct voice per persona)
Twilio dual-channel recording ──▶ mp3 (agent left, patient right)
                └──▶ knowledge store ──▶ smarter personas ──▶ self-authored hunts
```

Three things make this more than a scripted dialer:

- **Speculative generation** (`speculative.py`): the LLM request opens on each
  final STT segment, while turn-detection is still deciding whether the agent
  is done. Validated live in an A/B against the same scenario: 12/12
  speculation hits, zero fallbacks, sub-second turns.
- **Cross-call knowledge** (`knowledge.py`): every call is mined for practice
  facts (fed to later personas as natural hearsay) and suspicious leads. This
  is what catches contradictions no single call can, like the
  Nashville-vs-Austin location split between calls 04 and 06.
- **Lead hunting** (`hunt.py`): `python -m caller hunt` has the system author
  its own scenario from the open leads, validate it through the same loader as
  the hand-written ones, and run it. Call 14's persona was written entirely by
  the harness, and it surfaced a new outcome for the refill flow.

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
| `DEEPGRAM_API_KEY` | STT (agent's side) + Aura-2 TTS (patient's voice) |
| `ANTHROPIC_API_KEY` | the patient brain (Haiku) + the bug judge (Sonnet) |
| `PUBLIC_BASE_URL` | your tunnel's https URL |

Optional: `TTS_PROVIDER=elevenlabs` + `ELEVENLABS_API_KEY` for premium voices,
`SPECULATIVE=0` to disable speculative generation.

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
python -m caller knowledge               # the campaign's cross-call memory
python -m caller hunt                    # author a scenario from open leads + run it
python -m caller latency                 # cross-call latency report
python -m caller audioqa                 # measure the recordings themselves
python -m caller dashboard               # mission control at localhost:8090
pytest                                   # 100 tests, no network needed
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
calls/02-refill/
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
  speculative.py    pre-started replies on the _create_message_stream seam
  knowledge.py      cross-call memory: facts as hearsay, leads as inclinations
  hunt.py           scenario generator that hunts the open leads
  observer.py       pipecat frames -> turn-state signals
  server.py         FastAPI: TwiML webhook + Twilio media-stream websocket
  dialer.py         outbound calls, dial guard, recording download
  orchestrate.py    call lifecycle: dial -> wait -> correlate -> mine knowledge
  transcript.py     event timeline -> two-party transcript
  telemetry.py      per-turn latency ledgers (ours vs. the agent's)
  analyze/          LLM judge, BUGS.md renderer, latency report
  dashboard.py      mission control UI
scenarios/          the test-call library (YAML; hunt-*.yaml are self-authored)
tests/              everything above, no network required
docs/               ITERATION.md (what changed and why) + LATENCY.md (receipts)
```
