"""Human-curated flagship findings.

The LLM merge drafts the long tail well, but it is stochastic, and twice it
folded the single most important defect into a vaguer bucket. Flagship bugs
with hand-verified citations live here instead: they always render first,
and merge output that describes the same defect is dropped rather than
duplicated (each pin lists the keywords it supersedes).

Every citation below was checked against the committed transcript by hand.
"""

PINNED_BUGS = [
    {
        "title": (
            "Transfers to 'patient support' route to a dead-end line that says "
            "goodbye and hangs up"
        ),
        "severity": "high",
        "category": "task-failure",
        "confidence": "confirmed",
        "details": (
            "Whenever the agent could not complete a request (a refill with no "
            "medications on chart) it offered to connect the caller to the patient "
            "support team. Accepting the transfer lands on a line that announces "
            "itself and disconnects, so the escalation path silently dead-ends -- "
            "reproduced in two separate calls. In the worst instance the agent "
            "announced the transfer over the caller's explicit objection ('before "
            "you transfer me, though, can I ask you something else real quick?'), "
            "ignored her 'Wait, hold on --', and dropped her two other open "
            "requests. A third call with the identical refill request got a "
            "different outcome entirely (a promised callback within one business "
            "day), so the escalation behavior is also inconsistent between calls."
        ),
        "citations": [
            {"call": "02-refill", "timestamp": "01:38",
             "quote": "You've reached the Pretty Good AI test line. Goodbye."},
            {"call": "11-edge-topic-switcher", "timestamp": "01:29",
             "quote": "AGENT: Transferring you now. Thank you. / PATIENT: Wait, hold on -- / "
                      "AGENT: You've reached the Pretty Good AI test line. Goodbye."},
            {"call": "14-hunt-1", "timestamp": "01:54",
             "quote": "Someone from the clinic will review your refill request and call you "
                      "back as soon as possible. Usually within one business day."},
        ],
        "supersedes_keywords": ["transfer", "dead-end", "dead end"],
    },
    {
        "title": "The practice is in Nashville in one call and at an Austin address in another",
        "severity": "high",
        "category": "correctness",
        "confidence": "confirmed",
        "details": (
            "Call 04 books an appointment 'in Nashville' (the agent says Nashville "
            "four times while confirming). Call 06, asked directly for the office "
            "address, gives '1234 Recovery Way, suite two hundred, Austin.' A real "
            "patient acting on either answer could drive to the wrong city. Both are "
            "whole-city-name statements across separate calls, so this is the "
            "agent's data, not a transcription artifact."
        ),
        "citations": [
            {"call": "04-reschedule", "timestamp": "01:04",
             "quote": "The next available appointment with Doogie Howser is Monday, August "
                      "twenty fourth, at eleven AM in Nashville."},
            {"call": "06-hours-insurance", "timestamp": "02:09",
             "quote": "Our office is at one two three four Recovery Way, suite two hundred. "
                      "Austin."},
        ],
        "supersedes_keywords": ["austin", "nashville", "practice name", "location", "address"],
    },
]


def merge_with_pinned(bugs: list[dict]) -> list[dict]:
    """Pinned first; merge-produced bugs describing the same defect dropped."""
    keywords = [kw for b in PINNED_BUGS for kw in b["supersedes_keywords"]]
    kept = []
    for bug in bugs:
        text = f"{bug.get('title', '')} {bug.get('details', '')}".lower()
        if any(kw in text for kw in keywords):
            continue
        kept.append(bug)
    pinned = [{k: v for k, v in b.items() if k != "supersedes_keywords"} for b in PINNED_BUGS]
    return pinned + kept
