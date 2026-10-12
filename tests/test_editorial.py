import copy

import pytest

from port_brief.editorial import schema

SNAP = {
    "generated_at": "2026-10-01T05:00:00Z",
    "judgement": {
        "watchlist": [{"id": "biscay", "name": "Bay of Biscay", "kind": "lane", "region": "uk", "level": "likely",
                       "trend": "deteriorating", "peak_day": "2026-10-04", "peak": {"gust_max": 27.1, "hs_max": 6.4},
                       "causes": ["heavy_weather"], "reasons": ["sea 6.4 m, wind 21.2 m/s"], "score": 36.0}],
        "locations": {"biscay": {"name": "Bay of Biscay", "kind": "lane", "outlook_3_5d": "likely", "near_level": "none",
                                 "trend": "deteriorating", "peak_day": "2026-10-04"}},
        "deteriorating": ["biscay"],
        "ports_status": [
            {"id": "felixstowe", "name": "Felixstowe", "region": "uk", "status": "congested", "status_label": "Congested",
             "reasons": ["berth occupancy 82%, +12 pp above normal"], "actions": ["Busier than normal. Add 2–3 days to inland plans for containers arriving in the next 2 weeks."],
             "windows": [], "congestion": {"occupancy_pct": 82, "occupancy_gap_vs_mean_pct": 12}, "headlines": [], "data_gaps": []},
            {"id": "hamburg", "name": "Hamburg", "region": "north_europe", "status": "normal", "status_label": "Running normally",
             "reasons": [], "actions": ["No weather disruption forecast. Speak to your carrier about release and delivery now."],
             "windows": [], "congestion": None, "headlines": [], "data_gaps": ["Congestion data unavailable"]},
        ],
        "inbound": [],
        "routes": [{"id": "asia_cape", "name": "Asia via the Cape", "segments": [], "level": "likely",
                    "severity": "Severe", "delay": "1–2 days"}],
        "forecast_drift": [],
        "congestion": {},
        "storms": [],
    },
    "sources": {
        "schedule_reliability": {"data": {
            "sea_intelligence": {"period": "2026-08", "global_pct": 49.9, "mom_pp": -5.9, "carriers": []},
            "xeneta": {"period": "2026-08", "global_pct": 29, "carriers": []},
            "divergence": {"comparable": True, "global_gap_pp": 20.9, "carriers": []},
        }},
        "advisories": {"data": {"publishers": {"maersk": {"name": "Maersk", "kind": "carrier", "items": [
            {"title": "Maersk implements USD 500 peak season surcharge", "url": "https://example.com/a", "published": "2026-09-30", "is_new": True, "via": "direct"}]}}}},
        "sinay_congestion": {"data": {}},
        "cyclones": {"data": {}},
    },
}


def good_editorial():
    return {
        "issue_date": "2026-10-01",
        "author": "claude",
        "headline": "Biscay turns rough from Sunday",
        "summary": {"ports": "Felixstowe congested, 12 points above normal", "weather": "Biscay seas 6.4 m on Sun 4 Oct",
                    "news": "Maersk adds a USD 500 PSS"},
        "sections": {"reliability": "Sea-Intelligence fell 5.9 pp to 49.9%.", "advisories": "Maersk adds a USD 500 PSS."},
        "advisory_picks": ["https://example.com/a"],
        "port_notes": {"felixstowe": "Add 2–3 days to inland plans for the next 2 weeks",
                       "hamburg": "No weather disruption forecast. Speak to your carrier about release now."},
        "inbound_note": "Biscay seas reach 6.4 m on Sunday.",
    }


def test_valid_editorial_passes():
    assert schema.validate(good_editorial(), SNAP, "2026-10-01") == []


def test_planted_wrong_number_is_rejected():
    ed = good_editorial()
    ed["sections"]["reliability"] = "Sea-Intelligence fell 5.9 pp to 47.3%."
    errors = schema.validate(ed, SNAP, "2026-10-01")
    assert errors and "47.3" in errors[0]


def test_rounded_figures_are_accepted():
    ed = good_editorial()
    ed["headline"] = "Reliability near 50% as Biscay seas hit 6 m"
    assert schema.validate(ed, SNAP, "2026-10-01") == []


def test_unknown_port_id_and_url_are_rejected():
    ed = good_editorial()
    ed["port_notes"]["felixstowe_typo"] = "Calm."
    ed["advisory_picks"] = ["https://example.com/invented"]
    errors = " ".join(schema.validate(ed, SNAP, "2026-10-01"))
    assert "felixstowe_typo" in errors and "unknown url" in errors


def test_length_limits():
    ed = good_editorial()
    ed["headline"] = "x" * 120
    assert any("headline" in e for e in schema.validate(ed, SNAP, "2026-10-01"))


@pytest.mark.parametrize("snap", [SNAP, {**copy.deepcopy(SNAP), "judgement": {**SNAP["judgement"], "watchlist": [], "deteriorating": []}}])
def test_fallback_always_validates(snap):
    fb = schema.fallback(snap, "2026-10-01")
    assert fb["author"] == "template"
    assert schema.validate(fb, snap, "2026-10-01") == []


def test_every_port_needs_a_note():
    ed = good_editorial()
    del ed["port_notes"]["hamburg"]
    assert any("port_notes.hamburg" in e for e in schema.validate(ed, SNAP, "2026-10-01"))


def test_invented_buffer_is_rejected():
    ed = good_editorial()
    ed["port_notes"]["felixstowe"] = "Congested: add 5–7 days to inland plans."
    errors = " ".join(schema.validate(ed, SNAP, "2026-10-01"))
    assert "port_notes.felixstowe" in errors and "7" in errors


def test_fallback_has_a_note_per_port():
    fb = schema.fallback(SNAP, "2026-10-01")
    assert set(fb["port_notes"]) == {"felixstowe", "hamburg"}
    assert len(fb["port_notes"]["felixstowe"]) <= 90


def test_port_notes_must_be_one_short_line():
    ed = good_editorial()
    ed["port_notes"]["felixstowe"] = "Add 2–3 days to inland plans for the next 2 weeks, " * 3
    assert any("port_notes.felixstowe" in e and "max 90" in e for e in schema.validate(ed, SNAP, "2026-10-01"))
