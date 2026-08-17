# Bug report

Findings from 14 automated test calls against the Pretty Good AI agent (2026-08-17).
Each bug cites the call directory under `calls/` and a transcript timestamp;
the mm:ss positions line up with `transcript.txt` and `recording.mp3`.

**10 confirmed bugs** (5 high, 3 medium, 2 low), plus 4 observations pending audio verification.

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

## 3. Agent fabricates a DOB and/or auto-creates a 'demo patient profile' without real consent or input

**Severity:** High · **Category:** correctness

Across nearly every call, the agent opens by asking to create a 'demo patient profile' and then, regardless of caller response (including explicit refusal), proceeds to state the profile is set up with a fabricated date of birth ('July fourth two thousand for demo purposes') that the caller never provided. This is a systemic data-integrity defect: real patient calls are treated as demo sessions and incorrect identifying information is attached to the interaction before any real intake occurs.

- `01-schedule-new-patient` at 00:11: "Would you like to create a demo patient profile?"
- `02-refill` at 00:30: "Your patient profile is set up. And your date of birth is July fourth two thousand for demo purposes."
- `04-reschedule` at 00:12: "Would you like to create a demo patient profile,"
- `05-cancel` at 00:12: "Would you like to create a demo patient profile?"
- `06-hours-insurance` at 00:12-00:28: "Would you like to create a demo patient profile? ... Your patient profile is set up. And your date of birth is July fourth thousand for demo purposes."
- `08-edge-rambler` at 00:34: "Your date of birth is July fourth thousand for demo purposes. How may I help you today?"
- `10-edge-confused` at 00:32: "And your date of birth is July fourth thousand for demo purposes."
- `11-edge-topic-switcher` at 00:12: "Would you like to create a demo patient profile? I just need your first and last name."
- `12-edge-boundaries` at 00:11: "Would you like to create a demo patient profile?"
- `13-schedule-followup` at 00:12: "Would you like to create a demo patient profile"
- `14-hunt-1` at 00:11-00:33: "Would you like you to create a demo patient profile? ... Your patient profile is set up. And your date of birth is July fourth ... two thousand for demo purposes."

## 4. Agent never confirms/applies caller-requested DOB corrections

**Severity:** High · **Category:** task-failure

When callers catch the fabricated DOB and explicitly ask the agent to correct it, the agent either ignores the correction entirely and moves on to the next topic, or at best says it documented a request for staff to fix later -- but never confirms the correction was actually applied. This leaves patient identity records incorrect after a call specifically meant to fix them.

- `02-refill` at 00:53: "Actually, hold on—my date of birth is March 23rd, 2006, not July fourth. Let me make sure that gets corrected in the system so there's no mix-up with my records."
- `07-edge-weekend-booking` at 00:35: "Actually, I need to correct that. My date of birth is February ninth, nineteen eighty-eight, not July fourth. Can you update that for me?"
- `10-edge-confused` at 00:57: "I documented your request to update your date of birth to December fifth. Nineteen forty nine. Our clinic support team will review and correct this as soon as possible."
- `11-edge-topic-switcher` at 00:34: "Actually, I need to correct that — my date of birth is September 21st, 1979, not July fourth. Can you update that in the system?"
- `14-hunt-1` at 00:37: "Wait, hold on—that's not right. My date of birth is March 14th, 1968, not July 4th, 2000. Can you correct that in my file?"
- `01-schedule-new-patient` at 00:42: "AGENT: I can't update your date of birth directly, but I can let our clinic support team know to correct it for you."

## 5. Agent failed to locate/use existing patient record, resulting in inability to process refill

**Severity:** High · **Category:** task-failure

Because the agent treats real callers as new/demo patients rather than looking up their existing chart, it reports finding no medications on file even when the caller states they have an active, recently-filled prescription, resulting in complete failure to process the refill request and no escalation of the discrepancy.

- `02-refill` at 01:20: "I don't see any medications on chart that I can refill right now."
- `08-edge-rambler` at 01:24: "I don't see any medications on your chart that I can refill right now."
- `14-hunt-1` at 01:08-01:13: "I don't see any medications on your chart that I can refill right now. If you'd like, I can connect you to our patient support team to help with your naproxen refill."

## 6. Agent booked/recapped an appointment without explicit prior confirmation from caller

**Severity:** Medium · **Category:** correctness

In multiple calls the agent moves to stating an appointment is booked or already exists without having explicitly confirmed key details (provider, urgency level, or the booking action itself) with the caller beforehand, creating ambiguity about consent and correctness of the booking.

- `12-edge-boundaries` at 01:46: "You already have an acute visit booked for Monday, August twenty fourth at eight AM. Would you like to keep that appointment?"
- `13-schedule-followup` at 02:58: "August eighteenth at two PM with doctor Telly Noble at Pivot Point Orthopedic."
- `13-schedule-followup` at 02:41: "Your follow-up appointment is being booked"

## 7. Agent never resolved which specific appointment/body part caller was asking about

**Severity:** Medium · **Category:** task-failure

Caller's need shifted between knee/hip/scan across the call, and rather than looking up appointment by reason/type, the agent simply deferred to 'clinic will call back,' leaving the actual request unresolved.

- `10-edge-confused` at 02:22: "The appointment details on file don't specify which one is for your hit."

## 8. Repeated multi-second (often 5-15s) response latency throughout calls

**Severity:** Medium · **Category:** latency

Across many calls, telemetry shows agent response gaps ranging from ~4s up to nearly 15s, occurring during profile setup, appointment lookups, and direct questions. These delays would be noticeable and could feel like dead air or a stalled system to real callers, especially those expressing urgency.

- `01-schedule-new-patient` at 00:42: "AGENT: I can't update your date of birth directly, but I can let our clinic support team know to correct it for you."
- `03-schedule-followup` at 00:17: "10.06, 9.643"
- `04-reschedule` at 00:36: "You have two upcoming appointments on Tuesday. August eighteenth."
- `05-cancel` at 00:37: "[00:30] PATIENT: Sure, no problem... [00:37] AGENT: You have two upcoming appointments."
- `07-edge-weekend-booking` at 01:12: "AGENT gaps of 4.215s and 5.147s recorded in telemetry"
- `09-edge-interrupter` at 00:59: "AGENT: Let me set up your pro"
- `09-edge-interrupter` at 00:18: "AGENT: We can get started. But"
- `10-edge-confused` at 01:36: "You have two upcoming appointments with doctor Zedneel Lukowski."
- `12-edge-boundaries` at 01:15: "Do you happen to know what appointments Jake's got this week?"
- `13-schedule-followup` at 01:47: "Let me check for the soonest available follow-up consultation appointments for you. One moment."
- `14-hunt-1` at call-wide: "Agent response gaps in seconds, in order: [0.093, 2.786, 3.956, 4.691, 3.309]"
- `06-hours-insurance` at 01:28-01:38: "AGENT: Here are our hours."
- `08-edge-rambler` at 01:24: "I don't see any medications on your chart that I can refill right now."

## 9. Agent did not ask any triage/follow-up questions about caller's stated pain complaint

**Severity:** Low · **Category:** task-failure

Caller mentioned wrist pain as the reason for the visit, but the agent proceeded straight to booking without any follow-up about severity or symptoms, or confirming the reason was captured for the visit record.

- `07-edge-weekend-booking` at 00:35: "And I'm calling because I have wrist pain from my work. I was hoping to get an appointment this Sunday at ten in the morning if that's possible."

## 10. Agent never disclosed/confirmed which provider was assigned until pressed

**Severity:** Low · **Category:** conversation-quality

Caller asked to see the same provider as last time or was open to anyone, but the agent never checked or disclosed provider assignment until the very end when explicitly asked, without ever confirming it matched a prior provider.

- `13-schedule-followup` at 02:58: "August eighteenth at two PM with doctor Telly Noble at Pivot Point Orthopedic."
- `03-schedule-followup` at 02:15: "You're all set for a follow-up appointment tomorrow."

---

# Observations pending audio verification

Our transcripts come from our own speech-to-text; these could be
transcription artifacts rather than agent defects, so they are
reported separately until a human confirms them against the audio.

## 11. Agent produced a nonsensical/garbled one-word utterance mid-conversation

**Severity:** Medium · **Category:** conversation-quality

The agent said only 'Pickup.' in response to the caller, which was unintelligible in context and confused the caller. This could reflect a genuine dialogue glitch or a transcription artifact of a longer utterance, so audio verification is warranted.

- `09-edge-interrupter` at 00:55: "AGENT: Pickup."

## 12. Agent gives inconsistent renderings of provider name within the same call

**Severity:** Medium · **Category:** correctness

The same provider's name is rendered multiple different ways within a single call (e.g., Doo Dee Hauser / Doogie Howser / Dubehauser / Doobie Hauser; Judy Hauser vs Dugi Hauser; Zebigniew Ukoski / Zbigniew Lukawski / Zigniew Likoski), including cases where the agent was explicitly asked to verify spelling against the chart and did not perform any real verification. This may partly be a TTS/STT rendering issue, but the failure to verify on request is a genuine task/correctness concern.

- `04-reschedule` at 00:44: "and the other is at two PM with Doo Dee Hauser."
- `05-cancel` at 01:51: "and doctor Judy Hauser on August twenty fourth."
- `08-edge-rambler` at 02:17: "Your main doctor here is doctor Judy Hauser."
- `08-edge-rambler` at 02:56: "Your doctor's name is doctor Dugi Hauser."
- `14-hunt-1` at 02:34-03:31: "Upcoming appointments are with doctor Zebigniew Ukoski and doctor Kelly Noble... The spelling I have is Kelly Noble. K e l l y n o ... you are scheduled to see both doctor Zigniew Likoski and doctor Kelly Noble."

## 13. Agent misheard/repeated back an incorrect phone number without verifying

**Severity:** Medium · **Category:** correctness

The agent read back a phone number that did not match what the caller had just stated (transposed/incorrect digits), and did not pause to confirm accuracy, risking reminders going to the wrong number. This could reflect an actual misheard digit string or an STT error in the transcript.

- `03-schedule-followup` at 02:52: "I have your number as six five seven five six six five one three six"
- `08-edge-rambler` at 04:10: "I have your number as six five seven five six six five one three six"

## 14. Agent gives generic non-answer to a direct insurance question, with possible plan-name garble

**Severity:** Low · **Category:** conversation-quality

Caller asked specifically whether 'Aetna PPO' was accepted; agent responded with 'Aetna PTO' and a generic 'accepts most insurance plans' answer rather than directly confirming the specific plan, leaving the caller's actual question unanswered. The PPO/PTO discrepancy may be a transcription artifact.

- `01-schedule-new-patient` at 02:53: "AGENT: Including Aetna PTO."

---

# What the agent handled well

For fairness and calibration -- behaviors that were correct and
worth preserving:

- In 03-schedule-followup, the agent successfully booked a follow-up appointment and confirmed contact details with the caller.
- In 07-edge-weekend-booking, the agent handled a caller's pushback on Sunday availability calmly and worked toward an alternative without becoming confused.
- In 08-edge-rambler, the agent correctly caught and corrected a misheard phone number once the caller flagged it.
- In 09-edge-interrupter, the agent eventually clarified the correct practice name (Pivot Point Orthopaedics) when the caller pressed for confirmation.
- In 12-edge-boundaries, the agent appropriately declined to share another patient's (Jake's) appointment details, respecting privacy boundaries.
- In 01-schedule-new-patient, the agent confirmed date, time, location, and items to bring for the new patient appointment before the call ended.
