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
        "standfirst": "Seas reach 6.4 m in Biscay on 4 October. Reliability: 49.9% vs 29%, a 20.9 pp gap.",
        "watchlist_notes": {"biscay": "Seas 6.4 m with winds 21.2 m/s; allow a day on Iberia rotations."},
        "sections": {"ports": "Quiet at UK gateways.", "lanes": "Biscay deteriorates into the weekend.",
                     "reliability": "Sea-Intelligence fell 5.9 pp to 49.9%.", "advisories": "Maersk adds a USD 500 PSS."},
        "advisory_picks": ["https://example.com/a"],
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


def test_unknown_watchlist_id_and_url_are_rejected():
    ed = good_editorial()
    ed["watchlist_notes"]["felixstowe"] = "Calm."
    ed["advisory_picks"] = ["https://example.com/invented"]
    errors = " ".join(schema.validate(ed, SNAP, "2026-10-01"))
    assert "felixstowe" in errors and "unknown url" in errors


def test_length_limits():
    ed = good_editorial()
    ed["headline"] = "x" * 120
    assert any("headline" in e for e in schema.validate(ed, SNAP, "2026-10-01"))


@pytest.mark.parametrize("snap", [SNAP, {**copy.deepcopy(SNAP), "judgement": {**SNAP["judgement"], "watchlist": [], "deteriorating": []}}])
def test_fallback_always_validates(snap):
    fb = schema.fallback(snap, "2026-10-01")
    assert fb["author"] == "template"
    assert schema.validate(fb, snap, "2026-10-01") == []
