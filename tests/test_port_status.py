from datetime import datetime, timezone

from conftest import hourly_series, set_day

from port_brief.config import playbook as pb
from port_brief.config.locations import BY_ID
from port_brief.judgement import port_status as ps
from port_brief.judgement import weather_risk as wr

FXT = BY_ID["felixstowe"]


def gusts(series, day, start_h, end_h, value):
    for h in range(day * 24 + start_h, day * 24 + end_h):
        series["wind_gusts_10m"][h] = value
    return series


def test_window_in_uk_local_time_during_bst():
    s = gusts(hourly_series(start="2026-10-01"), 4, 9, 18, 21.0)  # 5 Oct 09:00-17:59 UTC
    w = wr.exceedance_windows(FXT, s)
    assert len(w) == 1
    assert w[0]["label"] == "Mon 5 Oct 10:00–19:00"  # BST = UTC+1
    assert w[0]["level"] == "likely" and w[0]["peak_gust"] == 21.0 and w[0]["hours"] == 9


def test_window_across_midnight_and_merge_small_gap():
    s = hourly_series(start="2026-10-01")
    gusts(s, 2, 21, 24, 16.0)
    gusts(s, 3, 1, 4, 16.0)  # one calm hour at 00:00 UTC is merged
    w = wr.exceedance_windows(FXT, s)
    assert len(w) == 1
    assert w[0]["label"] == "Sat 3 Oct 22:00 – Sun 4 Oct 05:00"
    assert w[0]["level"] == "watch"


def test_past_hours_are_ignored():
    s = gusts(hourly_series(start="2026-10-01"), 0, 2, 5, 22.0)
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert wr.exceedance_windows(FXT, s, now) == []


def port(assessment=None, congestion=None, headlines=()):
    return ps.assess_port(FXT, assessment, congestion, list(headlines))


def test_no_sinay_data_is_never_called_normal_congestion():
    r = port()
    assert r["status"] == "normal"
    assert r["data_gaps"] == [pb.NO_CONGESTION_DATA]
    assert r["actions"] == [pb.ACTIONS["normal_no_congestion"]]


def test_normal_with_data_says_release_now():
    r = port(congestion={"occupancy_pct": 60, "occupancy_gap_vs_mean_pct": 1.0})
    assert r["status"] == "normal" and r["actions"] == [pb.ACTIONS["normal"]]


def test_gap_of_ten_points_is_congested_with_buffer_advice():
    r = port(congestion={"occupancy_pct": 82, "occupancy_gap_vs_mean_pct": 10.0})
    assert r["status"] == "congested"
    assert "2–3 days" in r["actions"][0] and "next 2 weeks" in r["actions"][0]


def test_busy_gap_is_watch():
    assert port(congestion={"occupancy_pct": 70, "occupancy_gap_vs_mean_pct": 6.0})["status"] == "watch"


def test_long_time_in_port_is_congested():
    r = port(congestion={"occupancy_pct": 60, "occupancy_gap_vs_mean_pct": 0, "time_in_port_median_h": 50, "time_in_port_trailing_avg_h": 38})
    assert r["status"] == "congested" and "longer in port" in r["reasons"][0]


def test_weather_disruption_outranks_congestion_and_keeps_both_actions():
    s = gusts(hourly_series(start="2026-10-01"), 4, 9, 18, 21.0)
    a = {"windows": wr.exceedance_windows(FXT, s)}
    r = port(a, {"occupancy_pct": 82, "occupancy_gap_vs_mean_pct": 12.0})
    assert r["status"] == "disruption"
    assert "Mon 5 Oct 10:00–19:00" in r["actions"][0] and "haulier" in r["actions"][0]
    assert any("2–3 days" in x for x in r["actions"])


def test_strike_headline_is_disruption():
    r = port(headlines=[{"title": "Felixstowe dockers announce strike", "url": "u", "signal": "disruption"}])
    assert r["status"] == "disruption"


def test_non_operational_headlines_are_ignored():
    snap = {"sources": {"advisories": {"data": {"publishers": {"p": {"items": [
        {"title": "Temporary transformer relieves Rotterdam grid congestion", "url": "a"},
        {"title": "Rotterdam terminal congestion builds", "url": "b"}]}}}}}}
    found = ps.port_headlines(snap, BY_ID["rotterdam"])
    assert [h["url"] for h in found] == ["b"] and found[0]["signal"] == "congestion"


def test_inbound_lane_delay_uses_playbook():
    s = set_day(hourly_series(start="2026-10-01"), 3, wave_height=6.5)
    a = {"agulhas": wr.assess_location(BY_ID["agulhas"], s, [])}
    out = ps.inbound(a)
    assert out[0]["level"] == "likely" and out[0]["delay"] == pb.INBOUND_DELAY["likely"]
    assert "Cape" in out[0]["action"]
