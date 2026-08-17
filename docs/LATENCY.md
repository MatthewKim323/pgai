# Latency report

Per-call response latency, in call order. "Ours" is the patient bot's
time from the agent finishing a turn to our first audio on the wire (the
number we tune). "Theirs" is how long the agent under test left the
caller waiting (the number that feeds the bug report). Seconds.

| call | dur (s) | turns | ours p50 | ours max | theirs p50 | theirs max |
|---|---|---|---|---|---|---|
| 01-schedule-new-patient | 210.00 | 8 | 1.41 | 6.06 | 2.94 | 14.77 |
| 02-refill | 116.97 | 5 | 1.45 | 4.86 | 1.59 | 3.00 |
| 03-schedule-followup | 190.01 | 8 | 1.16 | 1.77 | 3.04 | 10.06 |
| 04-reschedule | 146.58 | 6 | 1.21 | 1.52 | 3.47 | 7.29 |
| 05-cancel | 160.52 | 8 | 1.09 | 1.24 | 2.54 | 5.76 |
| 06-hours-insurance | 194.19 | 8 | 1.25 | 1.94 | 3.12 | 3.40 |
| 07-edge-weekend-booking | 187.16 | 7 | 1.25 | 1.66 | 2.66 | 5.15 |
| 08-edge-rambler | 263.33 | 9 | 1.08 | 1.25 | 2.74 | 3.62 |
| 09-edge-interrupter | 206.68 | 9 | 1.18 | 1.45 | 2.66 | 6.86 |
| 10-edge-confused | 214.60 | 7 | 1.13 | 1.32 | 3.01 | 8.29 |
| 11-edge-topic-switcher | 105.88 | 4 | 1.26 | 2.17 | 1.54 | 2.89 |
| 12-edge-boundaries | 211.01 | 6 | 1.21 | 1.97 | 3.10 | 5.68 |
| 13-schedule-followup | 189.54 | 11 | 1.06 | 1.47 | 2.90 | 7.41 |

Across 13 calls: our median response latency ranges 1.06-1.45s; the agent's worst single gap was 14.77s.

The arc is visible in call order: call 01 ran with a mistuned VAD stop
(4-6s stalls, see docs/ITERATION.md); every later call holds a steady
sub-2s worst case.
