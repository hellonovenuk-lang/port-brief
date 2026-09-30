import json

from conftest import hourly_series, set_day

from port_brief import paths
from port_brief.config.locations import BY_ID
from port_brief.judgement import weather_risk as wr


def test_calm_port_has_no_flags():
    a = wr.assess_location(BY_ID["felixstowe"], hourly_series(), [])
    assert all(d["level"] == "none" for d in a["days"])
    assert a["trend"] == "stable"
    assert wr.watchlist([a]) == []


def test_crane_threshold_edges():
    loc = BY_ID["felixstowe"]
    s = hourly_series()
    set_day(s, 1, wind_gusts_10m=14.9)
    set_day(s, 2, wind_gusts_10m=15.0)
    set_day(s, 3, wind_gusts_10m=20.0)
    a = wr.assess_location(loc, s, [])
    assert [d["level"] for d in a["days"][1:4]] == ["none", "watch", "likely"]
    assert a["days"][3]["flags"][0]["type"] == "crane"


def test_pilot_long_period_swell_triggers_without_big_sea():
    s = set_day(hourly_series(), 4, swell_wave_height=2.6, swell_wave_period=13.0, wave_height=2.7)
    a = wr.assess_location(BY_ID["southampton"], s, [])
    flags = a["days"][4]["flags"]
    assert {"type": "pilot", "level": "likely"}.items() <= flags[0].items()


def test_deteriorating_trend_and_peak_day():
    s = set_day(hourly_series(), 4, wave_height=6.5, wind_speed_10m=18.0)
    a = wr.assess_location(BY_ID["biscay"], s, [])
    assert a["trend"] == "deteriorating"
    assert a["outlook_3_5d"] == "likely"
    assert a["peak_day"] == "2026-10-05"
    wl = wr.watchlist([a])
    assert wl[0]["id"] == "biscay" and wl[0]["causes"] == ["heavy_weather"]


def test_improving_when_bad_weather_is_now():
    s = set_day(hourly_series(), 0, wave_height=5.0)
    a = wr.assess_location(BY_ID["mid_north_atlantic"], s, [])
    assert a["near_level"] == "watch" and a["trend"] == "improving"


def test_agulhas_opposing_current_is_likely():
    s = set_day(hourly_series(), 3, wave_height=4.5, swell_wave_height=4.0, swell_wave_direction=230,
                ocean_current_direction=225, ocean_current_velocity=3.0)
    a = wr.assess_location(BY_ID["agulhas"], s, [])
    types = {f["type"]: f["level"] for f in a["days"][3]["flags"]}
    assert types["abnormal_waves"] == "likely"


def test_agulhas_swell_with_current_is_only_watch():
    s = set_day(hourly_series(), 3, wave_height=4.5, swell_wave_height=4.0, swell_wave_direction=230,
                ocean_current_direction=45, ocean_current_velocity=3.0)
    a = wr.assess_location(BY_ID["agulhas"], s, [])
    types = {f["type"]: f["level"] for f in a["days"][3]["flags"]}
    assert types["abnormal_waves"] == "watch"


def test_uk_relevance_ranks_above_equal_global_risk():
    s = set_day(hourly_series(), 4, wave_height=4.5)
    uk = wr.assess_location(BY_ID["western_approaches"], s, [])
    glob = wr.assess_location(BY_ID["suez"], s, [])
    assert [w["id"] for w in wr.watchlist([glob, uk])] == ["western_approaches", "suez"]


def test_cyclone_flag_counts_as_near_risk():
    storms = [{"name": "TEST-26", "severity": "Tropical Storm", "nearby": [{"id": "taiwan_strait", "distance_km": 400, "level": "likely"}]}]
    a = wr.assess_location(BY_ID["taiwan_strait"], hourly_series(), storms)
    assert a["near_level"] == "likely"
    assert wr.watchlist([a])[0]["causes"] == ["cyclone"]


def test_forecast_drift_between_runs(tmp_data):
    loc = BY_ID["felixstowe"]
    prev = hourly_series(start="2026-09-30", days=7)
    cur = set_day(hourly_series(start="2026-10-01", days=7), 2, wind_gusts_10m=14.0)  # 3 Oct gusts 8 -> 14
    paths.WEATHER_HISTORY.mkdir(parents=True)
    (paths.WEATHER_HISTORY / "2026-09-30T0500Z.json").write_text(json.dumps({"run_id": "2026-09-30T0500Z", "hourly": {"felixstowe": prev}}))
    prev_hourly, prev_run = wr.previous_weather("2026-10-01T0500Z")
    assert prev_run == "2026-09-30T0500Z"
    current = {"felixstowe": wr.assess_location(loc, cur, [])}
    drift = wr.forecast_drift(current, prev_hourly, prev_run)
    assert drift[0]["date"] == "2026-10-03" and drift[0]["gust_delta"] == 6.0


def test_null_marine_values_do_not_crash():
    s = hourly_series()
    s["wave_height"] = [None] * len(s["time"])
    s["swell_wave_height"] = [None] * len(s["time"])
    a = wr.assess_location(BY_ID["felixstowe"], s, [])
    assert a["days"][0]["hs_max"] is None
