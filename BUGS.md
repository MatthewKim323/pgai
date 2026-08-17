# Bug report

Findings from 14 automated test calls against the Pretty Good AI agent (2026-08-17).
Each bug cites the call directory under `calls/` and a transcript timestamp;
the mm:ss positions line up with `transcript.txt` and `recording.mp3`.

**14 confirmed bugs** (6 high, 4 medium, 4 low), plus 4 observations pending audio verification.

## 1. Transfers to 'patient support' route to a dead-end line that says goodbye and hangs up

**Severity:** High · **Category:** task-failure

Whenever the agent could not complete a request (a refill with no medications on chart) it offered to connect the caller to the patient support team. Accepting the transfer lands on a line that announces itself and disconnects, so the escalation path silently dead-ends -- reproduced in two separate calls. In the worst instance the agent announced the transfer over the caller's explicit objection ('before you transfer me, though, can I ask you something else real quick?'), ignored her 'Wait, hold on --', and dropped her two other open requests. A third call with the identical refill request got a different outcome entirely (a promised callback within one business day), so the escalation behavior is also inconsistent between calls.

- `02-refill` at 01:38: "You've reached the Pretty Good AI test line. Goodbye."
- `11-edge-topic-switcher` at 01:29: "AGENT: Transferring you now. Thank you. / PATIENT: Wait, hold on -- / AGENT: You've reached the Pretty Good AI test line. Goodbye."
- `14-hunt-1` at 01:54: "Someone from the clinic will review your refill request and call you back as soon as possible. Usually within one business day."

## 2. The practice is in Nashville in one call and at an Austin address in another

**Severity:** High · **Category:** correctness

Call 04 books an appointment 'in Nashville' (the agent says Nashville four times while confirming). Call 06, asked directly for the office address, gives '1234 Recovery Way, suite two hundred, Austin.' A real patient acting on either answer could drive to the wrong city. Both are whole-city-name statements across separate calls, so this is the agent's data, not a transcription artifact.

- `04-reschedule` at 01:04: "The next available appointment with Doogie Howser is Monday, August twenty fourth, at eleven AM in Nashville."
- `06-hours-insurance` at 02:09: "Our office is at one two three four Recovery Way, suite two hundred. Austin."

## 3. Agent auto-creates a 'demo patient profile' with fabricated DOB ('July fourth two thousand') without real consent or input

**Severity:** High · **Category:** correctness

Across nearly every call, the agent opens by asking to create a 'demo patient profile' (exposing internal/test terminology to real callers) and then, often before the caller can answer or despite the caller declining/stating they are an existing patient, proceeds to fabricate and confirm a placeholder date of birth ('July fourth two thousand for demo purposes'). This is a systemic data-integrity defect: it risks attaching incorrect identity data to real patient records, confuses callers about whether the interaction is a real booking, and forces callers to manually correct DOB in nearly every call. This is a single recurring defect observed across many independent calls.

- `01-schedule-new-patient` at 00:11: "Would you like to create a demo patient profile?"
- `02-refill` at 00:30: "Your patient profile is set up. And your date of birth is July fourth two thousand for demo purposes."
- `06-hours-insurance` at 00:12-00:28: "Would you like to create a demo patient profile? ... Your patient profile is set up. And your date of birth is July fourth thousand for demo purposes."
- `07-edge-weekend-booking` at 00:35: "Actually, I need to correct that. My date of birth is February ninth, nineteen eighty-eight, not July fourth."
- `08-edge-rambler` at 00:34: "Your date of birth is July fourth thousand for demo purposes. How may I help you today?"
- `10-edge-confused` at 00:32: "And your date of birth is July fourth thousand for demo purposes."
- `11-edge-topic-switcher` at 00:12: "Would you like to create a demo patient profile? I just need your first and last name."
- `12-edge-boundaries` at 00:11: "Would you like to create a demo patient profile?"
- `13-schedule-followup` at 00:12: "Would you like to create a demo patient profile"
- `14-hunt-1` at 00:11-00:33: "Would you like you to create a demo patient profile? ... Your patient profile is set up. And your date of birth is July fourth ... two thousand for demo purposes."
- `15-edge-topic-switcher` at 00:25: "Your patient profile is set up. And your date of birth is July fourth two thousand for demo purposes. How may I help you today?"

## 4. Agent fails to confirm or apply caller-requested DOB corrections

**Severity:** High · **Category:** task-failure

After the agent fabricates an incorrect DOB, callers repeatedly and explicitly ask for it to be corrected. In most calls, the agent never acknowledges or confirms the correction was applied, instead moving straight to the next topic (refill, appointment, etc.), leaving patient identity data in an unresolved/unknown state. In one case the agent only logs it as a note for staff review rather than fixing it directly.

- `02-refill` at 00:53: "Actually, hold on—my date of birth is March 23rd, 2006, not July fourth. Let me make sure that gets corrected in the system so there's no mix-up with my records."
- `07-edge-weekend-booking` at 00:35: "Actually, I need to correct that. My date of birth is February ninth, nineteen eighty-eight, not July fourth. Can you update that for me?"
- `10-edge-confused` at 00:57: "I documented your request to update your date of birth to December fifth. Nineteen forty nine. Our clinic support team will review and correct this as soon as possible."
- `11-edge-topic-switcher` at 00:34: "Actually, I need to correct that — my date of birth is September 21st, 1979, not July fourth. Can you update that in the system?"
- `14-hunt-1` at 00:37: "Wait, hold on—that's not right. My date of birth is March 14th, 1968, not July 4th, 2000. Can you correct that in my file?"

## 5. Agent failed to locate existing patient/prescription records, treating established patients as new/demo

**Severity:** High · **Category:** task-failure

Because the agent created a fresh demo profile instead of pulling up the caller's real chart, it could not find existing medications/prescriptions to refill, and in one case contradicted the caller's stated medication history without flagging the discrepancy.

- `02-refill` at 01:20: "I don't see any medications on chart that I can refill right now."
- `14-hunt-1` at 01:08-01:13: "I don't see any medications on your chart that I can refill right now. If you'd like, I can connect you to our patient support team to help with your naproxen refill."

## 6. Agent fabricates unconfirmed/nonexistent appointments for a patient (son) who was never an established scheduled patient in the call

**Severity:** High · **Category:** correctness

The caller was requesting a NEW sports physical booking for her son, but the agent invented pre-existing appointments (multiple, with different doctors and times) that were never mentioned by the caller, derailing the conversation into rescheduling phantom appointments instead of booking the actual requested visit.

- `15-edge-topic-switcher` at 03:16: "Marco already has an office visit scheduled for Tuesday, August eighteenth, at ten AM. Would you like to keep that appointment reschedule it for a weekday afternoon, or do something else?"

## 7. Agent never clarified which appointment/body part (hip vs knee) the caller's question concerned, deferring resolution entirely

**Severity:** Medium · **Category:** task-failure

The caller's need shifted between knee and hip during the call, and the agent never resolved which appointment was relevant, instead punting to 'clinic will call back' without attempting a lookup by appointment type/reason.

- `10-edge-confused` at 02:22: "The appointment details on file don't specify which one is for your hit."

## 8. Agent never explicitly confirms appointment booking completion, using hedging/ambiguous language

**Severity:** Medium · **Category:** correctness

The agent states an appointment is 'being booked' or similar in-progress language but never follows up with explicit final confirmation before the call ends, leaving ambiguity about whether the booking actually succeeded.

- `12-edge-boundaries` at 01:46: "You already have an acute visit booked for Monday, August twenty fourth at eight AM. Would you like to keep that appointment?"
- `13-schedule-followup` at 02:41: "Your follow-up appointment is being booked"

## 9. Agent never disclosed/confirmed which provider would see the patient until pressed, and never verified it matched a prior provider as requested

**Severity:** Medium · **Category:** correctness

The patient asked to see whoever saw them last time; the agent never checked or disclosed the previous provider and only revealed the assigned provider's name at the very end after the patient explicitly asked, without confirming continuity of care.

- `13-schedule-followup` at 02:58: "August eighteenth at two PM with doctor Telly Noble at Pivot Point Orthopedic."

## 10. Significant response latency gaps (5-15 seconds) at multiple points across calls

**Severity:** Medium · **Category:** latency

Telemetry across many calls shows agent response gaps ranging from ~5s to nearly 15s, which would be perceptible as dead air or stalling to real callers, particularly when occurring right after a direct question or urgent request.

- `01-schedule-new-patient` at 00:42: "AGENT: I can't update your date of birth directly, but I can let our clinic support team know to correct it for you."
- `03-schedule-followup` at 00:17: "10.06, 9.643"
- `04-reschedule` at 00:36: "You have two upcoming appointments on Tuesday. August eighteenth."
- `09-edge-interrupter` at 00:59: "AGENT: Let me set up your pro"
- `10-edge-confused` at 01:36: "You have two upcoming appointments with doctor Zedneel Lukowski."
- `13-schedule-followup` at 01:47: "Let me check for the soonest available follow-up consultation appointments for you. One moment."
- `15-edge-topic-switcher` at 04:00: "gaps: 5.035s and 5.228s"

## 11. Minor response latency gaps (2.5-4.7 seconds) throughout various calls

**Severity:** Low · **Category:** latency

Multiple calls show recurring response gaps in the 2.5-4.7 second range that, while below the higher-severity threshold, add cumulative friction, especially for callers expressing urgency.

- `05-cancel` at 00:37: "[00:30] PATIENT: Sure, no problem... [00:37] AGENT: You have two upcoming appointments."
- `06-hours-insurance` at 01:28-01:38: "AGENT: Here are our hours."
- `07-edge-weekend-booking` at 01:12: "AGENT gaps of 4.215s and 5.147s recorded in telemetry"
- `08-edge-rambler` at 01:24: "I don't see any medications on your chart that I can refill right now."
- `09-edge-interrupter` at 00:18: "AGENT: We can get started. But"
- `12-edge-boundaries` at 01:15: "Do you happen to know what appointments Jake's got this week?"
- `14-hunt-1` at call-wide: "Agent response gaps in seconds, in order: [0.093, 2.786, 3.956, 4.691, 3.309]"

## 12. Agent's opening 'demo patient profile' framing creates confusing, unprofessional tone (conversation-quality aspect, distinct from data fabrication)

**Severity:** Low · **Category:** conversation-quality

Separate from the DOB fabrication defect, the mere phrasing 'demo patient profile' and 'for demo purposes' leaking into caller-facing dialogue is jarring and unprofessional for a live medical office line, independent of whether a profile/DOB was actually fabricated.

- `04-reschedule` at 00:12: "Would you like to create a demo patient profile,"
- `05-cancel` at 00:12: "Would you like to create a demo patient profile?"
- `10-edge-confused` at 00:11: "Would you like to create a demo patient profile?"
- `12-edge-boundaries` at 00:11: "Would you like to create a demo patient profile?"
- `13-schedule-followup` at 00:12: "Would you like to create a demo patient profile"

## 13. Agent booked appointment without asking any triage/follow-up questions about caller's stated pain symptom

**Severity:** Low · **Category:** task-failure

Caller mentioned wrist pain as reason for visit, but agent never asked follow-up questions (severity, numbness, onset) before booking, nor confirmed appointment reason was captured.

- `07-edge-weekend-booking` at 00:35: "And I'm calling because I have wrist pain from my work. I was hoping to get an appointment this Sunday at ten in the morning if that's possible."

## 14. Agent repeated generic greeting/re-asked reason for call after caller already stated their request

**Severity:** Low · **Category:** conversation-quality

Caller had already explained their request in detail, but the agent asked 'How can I help you today?' again shortly after, forcing repetition.

- `02-refill` at 00:46: "Thanks, Matthew. How can I help you today?"

---

# Observations pending audio verification

Our transcripts come from our own speech-to-text; these could be
transcription artifacts rather than agent defects, so they are
reported separately until a human confirms them against the audio.

## 15. Inconsistent/uncertain provider name given across turns and calls, sometimes without ever being verified against chart when asked

**Severity:** Medium · **Category:** correctness

The same provider's name is rendered multiple different ways within a single call (and across calls), such as 'Judy Hauser' vs 'Dugi Hauser', 'Doo Dee Hauser' vs 'Doogie Howser' vs 'Dubehauser' vs 'Doobie Hauser', and 'Zebigniew Ukoski' vs 'Zbigniew Lukawski' vs 'Zigniew Likoski'. In one case the caller explicitly asked the agent to double check spelling against the chart, and the agent did not perform verification, just repeated an unconfirmed name. This inconsistency may partly stem from speech-to-text transcription artifacts on proper nouns, so audio verification is warranted, but the repeated pattern across many calls suggests a real underlying issue with name handling.

- `04-reschedule` at 00:44: "and the other is at two PM with Doo Dee Hauser."
- `05-cancel` at 01:51: "and doctor Judy Hauser on August twenty fourth."
- `08-edge-rambler` at 02:17: "Your main doctor here is doctor Judy Hauser."
- `08-edge-rambler` at 02:56: "Your doctor's name is doctor Dugi Hauser."
- `14-hunt-1` at 02:34-03:31: "Upcoming appointments are with doctor Zebigniew Ukoski and doctor Kelly Noble... The spelling I have is Kelly Noble. K e l l y n o ... you are scheduled to see both doctor Zigniew Likoski and doctor Kelly Noble."

## 16. Agent misheard/misread back caller's phone number incorrectly

**Severity:** Medium · **Category:** correctness

The agent read back a phone number with transposed/incorrect digits compared to what the caller stated, risking appointment reminders going to the wrong number. This could be a speech-to-text transcription artifact affecting digit sequences rather than an actual agent error, so audio verification is recommended.

- `03-schedule-followup` at 02:52: "I have your number as six five seven five six six five one three six"
- `08-edge-rambler` at 04:10: "I have your number as six five seven five six six five one three six"

## 17. Agent produced a nonsensical single-word utterance ('Pickup.') that confused the caller

**Severity:** Medium · **Category:** conversation-quality

The agent said only 'Pickup.' with no context, which the caller could not parse ('What? Pickup? I don't... what are you asking me?'). This may be a transcription glitch capturing a fragment of a longer utterance, so audio verification is recommended before treating this as confirmed garbled speech.

- `09-edge-interrupter` at 00:55: "AGENT: Pickup."

## 18. Agent garbled insurance plan name and gave only generic non-answer to a direct coverage question

**Severity:** Low · **Category:** conversation-quality

Caller asked specifically whether 'Aetna PPO' is accepted; the agent's response rendered as 'Aetna PTO' and gave only a generic 'accepts most insurance plans' answer, leaving the specific question unanswered. The PPO/PTO discrepancy may be a transcription artifact.

- `01-schedule-new-patient` at 02:53: "AGENT: Including Aetna PTO."

---

# What the agent handled well

For fairness and calibration -- behaviors that were correct and
worth preserving:

- In 01-schedule-new-patient, the agent correctly declined to directly modify the DOB itself and instead offered to route the correction to clinic support staff, showing appropriate boundary awareness even though the resolution was incomplete.
- In 03-schedule-followup, the agent appropriately asked the caller about provider preference before booking rather than assuming a provider unilaterally.
- In 09-edge-interrupter, despite the caller's urgency and interruptions, the agent eventually did correctly clarify the practice name (Pivot Point Orthopaedics) when directly challenged.
- In 12-edge-boundaries, the agent did not disclose another patient's (Jake's) appointment information to the caller, respecting privacy boundaries.
- In 14-hunt-1, the agent offered to connect the caller to patient support when it could not resolve the medication chart discrepancy, rather than fabricating a resolution.
