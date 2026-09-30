import json
from pathlib import Path

from port_brief import collect as collect_mod
from port_brief import paths
from port_brief.sources import advisories, schedule_reliability as sr
from port_brief.sources.base import Context, SourceResult, run_source

FIXTURES = Path(__file__).parent / "fixtures"


def test_sea_intelligence_workbook_parses_top13():
    wb = sr.parse_si_workbook((FIXTURES / "sea_intelligence_glp_2026-08.xlsx").read_bytes())
    assert wb["period"] == "2026-08"
    assert wb["series"]["2026-08"] == 49.9
    assert len(wb["carriers"]) == 13
    assert wb["carriers"][0] == {"rank": 1, "carrier": "Maersk", "pct": 67.3}
    assert wb["carriers"][-1]["carrier"] == "Wan Hai"


def test_xeneta_period_and_text_mentions():
    assert sr.xeneta_period("Xeneta Schedule Reliability Scorecard - August 2026") == "2026-08"
    assert sr.xeneta_period("Xeneta Schedule Reliability Scorecard - Q2 2026") == "2026-Q2"
    html = (FIXTURES / "xeneta_2026-08.html").read_text()
    text = sr.BeautifulSoup(html, "lxml").get_text(" ")
    mentions = sr.xeneta_text_mentions(text)
    assert any(k.endswith("maersk") and v == 51 for k, v in mentions.items())
    assert mentions.get("hapaglloyd") == 46


def test_divergence_is_computed_not_reconciled():
    si = {"period": "2026-08", "global_pct": 49.9, "carriers": [{"rank": 1, "carrier": "Maersk", "pct": 67.3}, {"rank": 8, "carrier": "OOCL", "pct": 41.5}]}
    xe = {"period": "2026-08", "global_pct": 29, "carriers": [{"rank": 1, "carrier": "Maersk", "pct": 51}]}
    dv = sr.divergence(si, xe)
    assert dv["global_gap_pp"] == 20.9
    assert dv["carriers"] == [{"carrier": "Maersk", "sea_intelligence_pct": 67.3, "xeneta_pct": 51, "gap_pp": 16.3,
                               "sea_intelligence_rank": 1, "xeneta_rank": 1}]
    assert sr.divergence(si, {**xe, "period": "2026-07"})["comparable"] is False


def test_advisory_relevance_filter():
    assert advisories.is_relevant("Maersk implements peak season surcharge on Europe-South Africa route")
    assert not advisories.is_relevant("Royal Caribbean ship returns to a different pier")


def test_failing_source_never_breaks_the_run(tmp_data, monkeypatch):
    def boom(ctx):
        raise RuntimeError("feed exploded")

    def fine(ctx):
        return SourceResult(source="x", data={"ok": True})

    monkeypatch.setattr(collect_mod, "SOURCES", {"marine_weather": fine, "cyclones": boom, "advisories": fine})
    snap = collect_mod.collect(Context(dry_run=False))
    assert snap["health"]["cyclones"]["status"] == "failed"
    assert "feed exploded" in snap["health"]["cyclones"]["errors"][0]
    assert snap["health"]["advisories"]["status"] == "ok"
    assert (paths.SNAPSHOTS / "latest.json").exists()
    log = [json.loads(line) for line in paths.FETCH_LOG.read_text().splitlines()]
    assert any(e.get("source") == "cyclones" and e.get("status") == "failed" for e in log)


def test_dry_run_without_cache_fails_cleanly(tmp_data):
    from port_brief.sources import cyclones

    result = run_source("cyclones", cyclones.fetch, Context(dry_run=True))
    assert result.status == "failed"
    assert "no cached response" in result.errors[0]
