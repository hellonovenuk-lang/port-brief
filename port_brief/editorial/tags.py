"""One tag per notice so readers can scan part 3: Disruption, Surcharge, Service change, Other."""

from __future__ import annotations

import re

TAGS = [
    ("disruption", "Disruption", ["strike", "industrial action", "walkout", "closure", "closed", "shut", "suspend",
                                  "congestion", "congested", "delay", "outage", "cyber", "storm", "backlog", "crisis"]),
    ("surcharge", "Surcharge", ["surcharge", "pss", "gri", "fak", "rates", "rate ", "fee", "tariff", "baf", "price"]),
    ("service", "Service change", ["service", "call", "route", "rotation", "resume", "vsa", "loop", "network",
                                   "launch", "adds", "restores", "transit", "omission", "blank"]),
]
TAG_COLOUR = {"disruption": "#b3261e", "surcharge": "#14365c", "service": "#2e7d32", "other": "#8a8a84"}


def tag_for(title: str) -> tuple[str, str]:
    low = title.lower()
    for key, label, words in TAGS:
        if any(re.search(r"\b" + re.escape(w.strip()) + r"(?:s|es|ed|d|ing)?\b", low) for w in words):
            return key, label
    return "other", "Other"
