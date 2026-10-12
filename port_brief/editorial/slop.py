"""Checks that keep machine-made tells out of Port Brief. See STYLE.md for the rules and reasons.

Two layers:
  text_issues / notes_issues  - the words (editorial fields), run by editorial.schema.validate
  render_issues               - the finished HTML and email, run by render.issue.render_issue,
                                so a template change cannot quietly bring a banned pattern back
"""

from __future__ import annotations

import html as html_lib
import re

TEXT_RULES = [
    (re.compile("—"), "em dash: use a full stop, comma or colon"),
    (re.compile(r"\b(it|this|that)(?:'s| is| was)\s+not\b[^.]{0,80}?[,;:]\s*(it|this|that)(?:'s| is| was)\b", re.I),
     "'it's not X, it's Y' construction"),
    (re.compile(r",\s+not\s+(?!yet\b|least\b|always\b|until\b)(?:a |an |the )?[a-z]+", re.I), "'X, not Y' construction"),
    (re.compile(r"\bnot (?:just|only|merely)\b[^.]{0,80}?\bbut\b", re.I), "'not just X but Y' construction"),
    (re.compile(r"\bno [^,.]{1,30}, no [^,.]{1,30}(?:,|\.)\s*just\b", re.I), "'no X, no Y, just Z' construction"),
    (re.compile(r"\b(?:delve|delves|delving|tapestry|landscape|seamless(?:ly)?|robust|pivotal|crucial|game[- ]changer|"
                r"unprecedented|navigate|navigating|ever-changing|ever-evolving|testament|underscores?|"
                r"in today's|it's worth noting|it is worth noting|at the end of the day|rest assured|buckle up|"
                r"to keep it that way|it goes without saying|in short|needless to say)\b", re.I),
     "stock phrase or filler"),
    (re.compile(r"[^.;]*;[^.;]*;"), "two or more semicolons in one sentence: split it"),
    (re.compile(r"\?"), "rhetorical question"),
    (re.compile(r"!"), "exclamation mark"),
]

# "Gusty Tue 16:00: allow 12 hours" - a label, a colon, then an instruction.
COLON_FORMULA = re.compile(r"^[^.]{3,60}?:\s+[a-z]")  # time colons (10:00) are never followed by a space
MAX_COLON_NOTES = 2

RENDER_RULES = [
    (re.compile(r"<h[1-6][^>]*>\s*(?:<[^>]+>\s*)*\d"), "numbered heading: section headings carry no numbers"),
    (re.compile("·"), "middle-dot chain: use commas or full stops"),
    (re.compile("[←-⇿]"), "arrow glyph: say it in words"),
    (re.compile(r"text-transform\s*:\s*uppercase", re.I), "uppercase labels"),
    (re.compile("[\U0001F300-\U0001FAFF☀-➿]"), "emoji or pictogram"),
    (re.compile("—"), "em dash"),
    # Repeating gradients draw hatch patterns (print-safe fills); a plain gradient is decoration.
    (re.compile(r"(?<!repeating-)linear-gradient\(", re.I), "decorative gradient"),
    (re.compile(r"box-shadow", re.I), "shadow"),
]


def text_issues(text: str) -> list[str]:
    found = []
    for rx, why in TEXT_RULES:
        m = rx.search(text or "")
        if m:
            found.append(f"{why} ({m.group(0).strip()[:40]!r})")
    return found


def notes_issues(notes: dict[str, str]) -> list[str]:
    formulaic = [k for k, v in notes.items() if COLON_FORMULA.search(v or "")]
    if len(formulaic) > MAX_COLON_NOTES:
        return [f"port_notes: {len(formulaic)} notes use the 'Label: instruction' formula "
                f"({', '.join(formulaic[:4])}); write plain sentences, situation first, then the action"]
    return []


def _visible_text(markup: str) -> str:
    markup = re.sub(r"<style.*?</style>|<svg.*?</svg>", " ", markup, flags=re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", markup))


def render_issues(markup: str) -> list[str]:
    """Design and copy tells in a rendered page (HTML) or plain-text email."""
    found = []
    no_svg = re.sub(r"<svg.*?</svg>", " ", markup, flags=re.S)
    for rx, why in RENDER_RULES:
        m = rx.search(no_svg)
        if m:
            found.append(f"{why} ({m.group(0)[:40]!r})")
    text = _visible_text(markup)
    for rx, why in TEXT_RULES:
        if why in ("rhetorical question", "exclamation mark"):
            continue  # notice headlines are quoted from publishers
        m = rx.search(text)
        if m and why != "stock phrase or filler":
            found.append(f"{why} ({m.group(0).strip()[:40]!r})")
    return found
