# Iteration log

What we heard on the wire, and what changed because of it. Newest first.

## After call 13 (`calls/13-schedule-followup`, speculative A/B)

Live validation of speculative generation against call 03 (same scenario,
same registered patient, no speculation): **12/12 speculation hits, zero
misses, zero fallbacks.** Median response latency 1.16s → 1.07s with
sub-second turns (best 0.73s), and `llm_first_token` fell to ~0.5s -- the
reply stream was already open when the turn committed, so what remains is
turn-commit machinery and TTS, not model wait. Flipped on by default
(`SPECULATIVE=0` to disable).

## After calls 07-12 (the edge gauntlet)

The scripted campaign closed at twelve calls, every one ending in a natural
patient goodbye or a documented remote hangup. The transfer dead-end became
the flagship finding with three recorded reproductions -- worst in call 11,
where the agent said "Transferring you now" over the caller's explicit
"before you transfer me, can I ask something else", ignored her "wait, hold
on", and dropped her two open requests. Call 12 balanced the report with
passes: the agent refused a third-party appointment lookup (privacy) and
triaged a possibly-broken ankle to immediate care -- and then referenced an
appointment the brand-new caller had never booked.

Cross-call knowledge (added mid-campaign, backfilled over calls 01-05)
started catching contradictions single calls can't: the practice is in
Nashville in call 03 and Austin in call 06; the provider's name renders
differently nearly every time it's spoken.

## After call 01 (`calls/01-schedule-new-patient`, 2026-08-17)

First live shakedown. The bot held a coherent 3.5-minute booking conversation
on the first attempt: gave a name, corrected the agent's wrong DOB, described
the complaint, picked a slot, asked about insurance, confirmed details back.

**Heard on our side:**

1. *Never said goodbye.* The call ended by watchdog hard-kill mid-flow
   (`ended_by: watchdog_timeout`). → Prompt now forbids inventing extra
   questions after the goal is met, and the watchdog got a two-stage design:
   a "wrap up now" system nudge at the scenario's time budget, hard EndFrame
   45s later.
2. *4–6s response stalls on turns 3 and 5.* Root cause from pipecat's own
   warning: VAD `stop_secs=0.4` exceeded the STT's p99, collapsing the
   transcript wait so turns stalled on the aggregator's 5s timeout.
   → `stop_secs` back to the recommended 0.2; smart-turn does the endpointing.
3. *Negative latencies in telemetry* on the interrupted turn. Marks that land
   before `agent_stop` on overlapped turns are bookkeeping noise. → Dropped
   from the ledger instead of averaged in.

**Heard on their side (bug-report material, judge will confirm):**

- 14.8s of dead air after the patient gave her name (00:15 → 00:37).
- Agent assigned a fabricated DOB ("July fourth two thousand, for demo
  purposes") the patient never gave, then said it couldn't correct it.
- Patient asked "do you take Aetna PPO?" before confirming the booking; agent
  booked first, answered later, and with "most insurance plans" vagueness
  (and the recording says "Aetna PTO").
- Provider name rendered inconsistently ("Abreaker" / "doctor Abricker").
