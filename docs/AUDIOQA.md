# Audio QA

Measured from the dual-channel recordings (left: agent, right: patient),
50ms RMS windows. 'Overlap' is double-talk as a share of all
speech; long mutual silences and heavy overlap are flagged for a human
ear-check. Note: the interrupter scenario overlaps by design.

| call | dur (s) | agent talk | patient talk | overlap | longest silence | flags |
|---|---|---|---|---|---|---|
| 01-schedule-new-patient | 210.5 | 58.8s | 56.7s | 0.2% | 9.5s | dead air 9.5s |
| 02-refill | 111.2 | 26.2s | 28.4s | 0.6% | 9.6s | dead air 9.6s |
| 03-schedule-followup | 197.4 | 61.1s | 34.1s | 0.0% | 9.9s | dead air 9.9s |
| 04-reschedule | 150.7 | 50.1s | 29.0s | 0.0% | 7.3s | dead air 7.3s |
| 05-cancel | 165.7 | 57.4s | 29.4s | 0.0% | 5.6s | ok |
| 06-hours-insurance | 201.7 | 58.7s | 63.1s | 0.2% | 3.4s | ok |
| 07-edge-weekend-booking | 193.7 | 58.5s | 51.8s | 0.3% | 4.9s | ok |
| 08-edge-rambler | 283.1 | 51.0s | 144.7s | 0.4% | 3.2s | ok |
| 09-edge-interrupter | 214.4 | 37.6s | 70.9s | 2.3% | 3.0s | ok |
| 10-edge-confused | 218.2 | 59.7s | 57.2s | 0.0% | 8.2s | dead air 8.2s |
| 11-edge-topic-switcher | 100.0 | 30.8s | 22.2s | 1.0% | 9.6s | dead air 9.6s |
| 12-edge-boundaries | 220.0 | 60.8s | 75.6s | 0.0% | 5.5s | ok |
| 13-schedule-followup | 195.5 | 72.5s | 26.4s | 0.6% | 7.1s | dead air 7.1s |
| 14-hunt-1 | 230.1 | 68.2s | 65.7s | 0.6% | 4.7s | ok |
