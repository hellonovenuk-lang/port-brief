from pathlib import Path

import pytest

from port_brief.editorial import slop

SAMPLES = Path(__file__).parent.parent / "samples"


@pytest.mark.parametrize("text", [
    "It's not a delay, it's a reset.",
    "Felixstowe is calm — for now.",
    "Weather flags are forecasts, not port notices.",
    "This is not just congestion but a backlog.",
    "No queues, no strikes, just calm.",
    "Liverpool stops Tue; six ports gusty; Gateway clear.",
    "Why wait to book?",
    "Shippers must navigate a shifting landscape.",
    "Book now to keep it that way.",
    "Book now!",
])
def test_writing_tics_are_caught(text):
    assert slop.text_issues(text)


@pytest.mark.parametrize("text", [
    "Cranes likely stop Tue 10:00–22:00. Warn your haulier and allow 24–48 hours.",
    "Congestion data is not yet connected, so statuses reflect weather only.",
    "Berths are busier than normal. Add 2–3 days to inland plans for the next 2 weeks.",
])
def test_plain_advice_passes(text):
    assert slop.text_issues(text) == []


def test_colon_formula_down_the_port_list_is_caught():
    notes = {f"p{i}": f"Gusty Tue {i}0:00: allow 12–24 hours" for i in range(1, 5)}
    assert slop.notes_issues(notes)
    assert slop.notes_issues({"a": "Gusty Tue. Allow 12 hours.", "b": "Clear. Book now."}) == []


@pytest.mark.parametrize("markup,why", [
    ("<h2>1 Port health</h2>", "numbered heading"),
    ("<h2><span class='part'>2</span>Weather</h2>", "numbered heading"),
    ("<p>84% · 38 h</p>", "middle-dot"),
    ("<p>Stay 38 h ↑</p>", "arrow"),
    ("<style>.x{text-transform: uppercase}</style>", "uppercase"),
    ("<style>.x{background: linear-gradient(red, blue)}</style>", "gradient"),
    ("<p>Weather flags are forecasts, not port notices.</p>", "'X, not Y'"),
])
def test_render_tells_are_caught(markup, why):
    assert any(why in issue for issue in slop.render_issues(markup))


def test_hatch_patterns_are_allowed():
    assert slop.render_issues("<style>.g{background: repeating-linear-gradient(135deg, #eee 0 1mm, #fff 1mm 2mm)}</style>") == []


@pytest.mark.parametrize("path", sorted(SAMPLES.glob("*/email.html")) + sorted(SAMPLES.glob("*/email.txt")))
def test_committed_samples_are_clean(path):
    assert slop.render_issues(path.read_text()) == []
