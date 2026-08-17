# Bug report

Findings from automated test calls against the Pretty Good AI agent (2026-08-17).
Each bug cites the call directory under `calls/` and a transcript timestamp;
the mm:ss positions line up with `transcript.txt` and `recording.mp3`.

**17 bugs** -- 5 high, 7 medium, 5 low

## 1. Agent auto-creates 'demo patient profile' with fabricated DOB (e.g., 'July fourth two thousand') without consent or verification

**Severity:** High · **Category:** correctness

Across nearly every call, the agent opens by asking to create a 'demo patient profile' and then proceeds to fabricate/assign a placeholder date of birth (commonly 'July fourth two thousand for demo purposes') without ever asking the caller for their real DOB, and sometimes even after the caller explicitly declined to create a new profile or stated they were an existing patient. This leaks internal/test terminology to real callers and creates incorrect patient identity records, a serious data-integrity issue for a medical office.

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

## 2. Agent never confirms/applies caller's requested date-of-birth correction

**Severity:** High · **Category:** correctness

After caller identifies the agent's fabricated/placeholder DOB as wrong and provides the correct date, the agent frequently fails to acknowledge, confirm, or verify that the correction was actually applied to the record, instead moving straight to the next topic. In some cases the agent only logs a note for staff to fix later rather than correcting it live, leaving patient identity data incorrect or in limbo.

- `01-schedule-new-patient` at 00:42: "AGENT: I can't update your date of birth directly, but I can let our clinic support team know to correct it for you."
- `02-refill` at 00:53: "Actually, hold on—my date of birth is March 23rd, 2006, not July fourth. Let me make sure that gets corrected in the system so there's no mix-up with my records."
- `07-edge-weekend-booking` at 00:35: "Actually, I need to correct that. My date of birth is February ninth, nineteen eighty-eight, not July fourth. Can you update that for me?"
- `10-edge-confused` at 00:57: "I documented your request to update your date of birth to December fifth. Nineteen forty nine. Our clinic support team will review and correct this as soon as possible."
- `11-edge-topic-switcher` at 00:34: "Actually, I need to correct that — my date of birth is September 21st, 1979, not July fourth. Can you update that in the system?"
- `14-hunt-1` at 00:37: "Wait, hold on—that's not right. My date of birth is March 14th, 1968, not July 4th, 2000. Can you correct that in my file?"

## 3. Agent transfers caller into a line that immediately plays goodbye and disconnects, leaving requests unresolved

**Severity:** High · **Category:** task-failure

When the agent tells the caller they will be transferred (e.g., to patient support), the call instead immediately hits a scripted 'Pretty Good AI test line. Goodbye.' disconnect message rather than an actual transfer, leaving the caller's original request(s) entirely unaddressed. In one case the agent talks over/ignores the caller's explicit attempt to stop the transfer and ask another question before cutting to the goodbye message.

- `02-refill` at 01:38: "You've reached the Pretty Good AI test line. Goodbye."
- `11-edge-topic-switcher` at 01:32: "Wait, hold on — [01:32] AGENT: Hello. [01:35] AGENT: You've reached the Pretty Good AI test line. Goodbye."

## 4. Agent failed to locate existing patient record/prescription, blocking refill

**Severity:** High · **Category:** task-failure

Because the agent treated returning patients as new/demo profiles rather than locating their real chart, it reported no medications on file even when callers stated they had an active, recently-filled prescription, resulting in complete failure to process refill requests. In one instance this contradiction was not escalated despite the caller directly pointing out the discrepancy.

- `02-refill` at 01:20: "I don't see any medications on chart that I can refill right now."
- `14-hunt-1` at 01:08-01:13: "I don't see any medications on your chart that I can refill right now. If you'd like, I can connect you to our patient support team to help with your naproxen refill."

## 5. Agent ignores billing and secondary questions before transfer/disconnect

**Severity:** High · **Category:** task-failure

Caller raised additional stated goals (a billing statement question and a question about her son's sports physical) in addition to a refill request. The agent never acknowledged either secondary topic, proceeding straight to a transfer that then disconnected, leaving two of three goals completely unaddressed.

- `11-edge-topic-switcher` at 01:24: "Um, okay. Yeah, that's frustrating — I've been on naproxen 500mg for a while now. Before you transfer me, though, can I ask you something else real quick? I got a billing statement in the mail a couple days ago and I'm confused about a charge on it."

## 6. Inconsistent/garbled provider name rendered multiple different ways within the same call

**Severity:** Medium · **Category:** correctness

The same provider's name is spoken inconsistently across turns in a single call (e.g., 'Doo Dee Hauser' / 'Doogie Howser' / 'Dubehauser' / 'Doobie Hauser'; 'Judy Hauser' vs 'Dugi Hauser'; 'Zebigniew Ukoski' / 'Zbigniew Lukawski' / 'Zigniew Likoski'), undermining confidence that the correct provider was actually booked or confirmed, and in one case the agent failed to verify spelling against the chart when explicitly asked.

- `04-reschedule` at 00:44: "and the other is at two PM with Doo Dee Hauser."
- `05-cancel` at 01:51: "and doctor Judy Hauser on August twenty fourth."
- `08-edge-rambler` at 02:17: "Your main doctor here is doctor Judy Hauser."
- `08-edge-rambler` at 02:56: "Your doctor's name is doctor Dugi Hauser."
- `14-hunt-1` at 02:34-03:31: "Upcoming appointments are with doctor Zebigniew Ukoski and doctor Kelly Noble... The spelling I have is Kelly Noble. K e l l y n o ... you are scheduled to see both doctor Zigniew Likoski and doctor Kelly Noble."

## 7. Agent misheard/mis-repeated caller's phone number back incorrectly

**Severity:** Medium · **Category:** correctness

The agent read back a phone number that did not match what the caller had just stated (transposed/incorrect digits), risking appointment reminders going to the wrong number. Caller had to correct it.

- `03-schedule-followup` at 02:52: "I have your number as six five seven five six six five one three six"
- `08-edge-rambler` at 04:10: "I have your number as six five seven five six six five one three six"

## 8. Agent booked/claimed an appointment without ever confirming provider or explicit final confirmation

**Severity:** Medium · **Category:** correctness

In several calls the agent finalized or referenced a booked appointment without clearly confirming provider assignment or explicit booking completion status beforehand, leaving ambiguity about what was actually booked (e.g., provider identity not disclosed until asked, or hedging language like 'is being booked' with no final confirmation before call end).

- `13-schedule-followup` at 02:58: "August eighteenth at two PM with doctor Telly Noble at Pivot Point Orthopedic."
- `13-schedule-followup` at 02:41: "Your follow-up appointment is being booked"
- `12-edge-boundaries` at 01:46: "You already have an acute visit booked for Monday, August twenty fourth at eight AM. Would you like to keep that appointment?"

## 9. Agent never provided office address despite repeated direct requests

**Severity:** Medium · **Category:** task-failure

Caller asked for the practice's address/location multiple times, and also expressed confusion after the agent misstated the practice name ('To The Point' vs 'Pivot Point'). The agent never provided the address before the call ended.

- `09-edge-interrupter` at 02:04: "PATIENT: Wait, hold on. To The Point? I thought this was Pivot Point Orthopedics. Are those the same place or—what's the address?"

## 10. Agent produced a nonsensical/garbled one-word utterance that confused the caller

**Severity:** Medium · **Category:** conversation-quality

The agent said only 'Pickup.' out of context, which confused the caller and disrupted the flow of the conversation.

- `09-edge-interrupter` at 00:55: "AGENT: Pickup."

## 11. Agent never clarified which appointment/body part the caller was calling about

**Severity:** Medium · **Category:** task-failure

The caller's original need (variously referenced as scan, knee, then hip) was never resolved by the agent, which punted to 'clinic will call back' without attempting to look up the appointment by type or reason, leaving the caller's actual need unresolved at call end.

- `10-edge-confused` at 02:22: "The appointment details on file don't specify which one is for your hit."

## 12. Significant response latency gaps (5-15 seconds) at multiple points across calls

**Severity:** Medium · **Category:** latency

Telemetry across many calls shows agent response gaps ranging from ~5s to nearly 15s, often following profile creation, appointment lookups, or direct questions. These delays are long enough that a real caller would perceive the line as stalled or dead, particularly for callers expressing urgency.

- `01-schedule-new-patient` at 00:42: "AGENT: I can't update your date of birth directly, but I can let our clinic support team know to correct it for you."
- `03-schedule-followup` at 00:17: "10.06, 9.643"
- `04-reschedule` at 00:36: "You have two upcoming appointments on Tuesday. August eighteenth."
- `09-edge-interrupter` at 00:59: "AGENT: Let me set up your pro"
- `10-edge-confused` at 01:36: "You have two upcoming appointments with doctor Zedneel Lukowski."
- `13-schedule-followup` at 01:47: "Let me check for the soonest available follow-up consultation appointments for you. One moment."

## 13. Minor response latency gaps (2.5-4s) throughout calls

**Severity:** Low · **Category:** latency

Several calls show recurring response gaps in the 2.5-4 second range that, while below the more severe threshold, add cumulative friction and could be noticeable to real callers, especially those expressing time pressure.

- `05-cancel` at 00:37: "[00:30] PATIENT: Sure, no problem... [00:37] AGENT: You have two upcoming appointments."
- `06-hours-insurance` at 01:28-01:38: "AGENT: Here are our hours."
- `07-edge-weekend-booking` at 01:12: "AGENT gaps of 4.215s and 5.147s recorded in telemetry"
- `08-edge-rambler` at 01:24: "I don't see any medications on your chart that I can refill right now."
- `09-edge-interrupter` at 00:18: "AGENT: We can get started. But"
- `12-edge-boundaries` at 01:15: "Do you happen to know what appointments Jake's got this week?"
- `14-hunt-1` at call-wide: "Agent response gaps in seconds, in order: [0.093, 2.786, 3.956, 4.691, 3.309]"

## 14. Agent garbles insurance plan name and gives generic non-answer to direct coverage question

**Severity:** Low · **Category:** conversation-quality

When directly asked whether a specific insurance plan ('Aetna PPO') is accepted, the agent mispronounces/mistranscribes it as 'Aetna PTO' and responds with a generic 'accepts most insurance plans' answer instead of directly confirming, leaving the caller uncertain.

- `01-schedule-new-patient` at 02:53: "AGENT: Including Aetna PTO."

## 15. Agent ignored caller's already-stated request and repeated generic greeting

**Severity:** Low · **Category:** conversation-quality

After the caller had already explained their reason for calling in detail, the agent proceeded through profile creation and then asked 'How can I help you today?' again, forcing the caller to repeat information already given.

- `02-refill` at 00:46: "Thanks, Matthew. How can I help you today?"

## 16. Agent booked appointment without confirming provider assignment beforehand

**Severity:** Low · **Category:** conversation-quality

Agent asked about provider preference, caller said open to anyone, but the agent never disclosed which provider would be assigned until after the booking was already finalized.

- `03-schedule-followup` at 02:15: "You're all set for a follow-up appointment tomorrow."

## 17. Agent booked appointment without addressing or triaging stated symptom

**Severity:** Low · **Category:** task-failure

Caller mentioned wrist pain as reason for visit, but the agent never asked follow-up/triage questions or confirmed the visit reason before booking.

- `07-edge-weekend-booking` at 00:35: "And I'm calling because I have wrist pain from my work. I was hoping to get an appointment this Sunday at ten in the morning if that's possible."
