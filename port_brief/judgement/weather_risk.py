"""Turn weather forecasts into a deterioration outlook.

Weather is a leading indicator, not a fact to report. For every port and lane this module
answers: how bad does it get, on which day, is it getting worse over the next 3-5 days,
and has the forecast itself moved since the previous run?
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from port_brief import paths
from port_brief.judgement import port_status
from port_brief.config.locations import AGULHAS, BY_ID, LOCATIONS, RELEVANCE, thresholds_for

LEVELS = {"none": 0, "watch": 1, "likely": 2}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}
DAYS = 7
DRIFT_GUST_MS = 3.0
DRIFT_HS_M = 1.0
UK_TZ = ZoneInfo("Europe/London")
WINDOW_MERGE_GAP_H = 2  # flagged hours this close together form one window


def _max(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def daily_peaks(hourly: dict, now: datetime | None = None) -> list[dict]:
    """Collapse an hourly series to per-UTC-day peaks. With `now`, today counts only the hours still ahead."""
    times = hourly.get("time") or []
    cutoff = now.strftime("%Y-%m-%dT%H:00") if now else None
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(times):
        if cutoff and t < cutoff:
            continue
        buckets[t[:10]].append(i)

    def col(name, idx):
        series = hourly.get(name) or []
        return [series[i] for i in idx if i < len(series)]

    days = []
    for day in sorted(buckets)[:DAYS]:
        idx = buckets[day]
        hs = col("wave_height", idx)
        peak_i = None
        if any(v is not None for v in hs):
            peak_i = max((i for i in idx if i < len(hourly["wave_height"]) and hourly["wave_height"][i] is not None),
                         key=lambda i: hourly["wave_height"][i])
        swell = col("swell_wave_height", idx)
        swell_i = None
        if any(v is not None for v in swell):
            swell_i = max((i for i in idx if hourly["swell_wave_height"][i] is not None), key=lambda i: hourly["swell_wave_height"][i])

        def at(name, i):
            s = hourly.get(name) or []
            return s[i] if i is not None and i < len(s) else None

        days.append({
            "date": day,
            "wind_max": _round(_max(col("wind_speed_10m", idx))),
            "gust_max": _round(_max(col("wind_gusts_10m", idx))),
            "hs_max": _round(_max(hs), 2),
            "swell_max": _round(_max(swell), 2),
            "swell_period_at_peak": _round(at("swell_wave_period", swell_i)),
            "swell_dir_at_peak": at("swell_wave_direction", swell_i),
            "wave_dir_at_peak": at("wave_direction", peak_i),
            "current_kmh_at_peak": at("ocean_current_velocity", peak_i),
            "current_dir_at_peak": at("ocean_current_direction", peak_i),
        })
    return days


def _round(v, nd=1):
    return round(v, nd) if isinstance(v, (int, float)) else None


def _ge(v, t):
    return v is not None and v >= t


def angle_diff(a, b) -> float:
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def day_flags(loc: dict, day: dict) -> list[dict]:
    """Operational flags for one location-day. Each flag: {type, level, reason}."""
    t = thresholds_for(loc)
    flags = []
    if loc["kind"] == "port":
        gust, wind = day["gust_max"], day["wind_max"]
        if _ge(gust, t["crane_likely_gust"]) or _ge(wind, t["crane_likely_wind"]):
            flags.append({"type": "crane", "level": "likely", "reason": f"gusts {gust} m/s, wind {wind} m/s"})
        elif _ge(gust, t["crane_watch_gust"]) or _ge(wind, t["crane_watch_wind"]):
            flags.append({"type": "crane", "level": "watch", "reason": f"gusts {gust} m/s, wind {wind} m/s"})

        hs, swell, period = day["hs_max"], day["swell_max"], day["swell_period_at_peak"]
        long_swell_likely = _ge(swell, t["pilot_likely_swell"]) and _ge(period, t["pilot_likely_period"])
        long_swell_watch = _ge(swell, t["pilot_watch_swell"]) and _ge(period, t["pilot_watch_period"])
        if _ge(hs, t["pilot_likely_hs"]) or long_swell_likely:
            flags.append({"type": "pilot", "level": "likely", "reason": f"sea {hs} m, swell {swell} m @ {period} s"})
        elif _ge(hs, t["pilot_watch_hs"]) or long_swell_watch:
            flags.append({"type": "pilot", "level": "watch", "reason": f"sea {hs} m, swell {swell} m @ {period} s"})
    else:
        hs, wind = day["hs_max"], day["wind_max"]
        if _ge(hs, t["lane_likely_hs"]) or _ge(wind, t["lane_likely_wind"]):
            flags.append({"type": "heavy_weather", "level": "likely", "reason": f"sea {hs} m, wind {wind} m/s"})
        elif _ge(hs, t["lane_watch_hs"]) or _ge(wind, t["lane_watch_wind"]):
            flags.append({"type": "heavy_weather", "level": "watch", "reason": f"sea {hs} m, wind {wind} m/s"})

        if loc.get("agulhas"):
            sdir, cdir, ckmh = day["swell_dir_at_peak"], day["current_dir_at_peak"], day["current_kmh_at_peak"]
            sw_swell = sdir is not None and AGULHAS["swell_from_min"] <= sdir <= AGULHAS["swell_from_max"] and _ge(hs, AGULHAS["min_hs"])
            if sw_swell:
                opposing = (cdir is not None and _ge(ckmh, AGULHAS["min_current_kmh"])
                            and angle_diff(cdir, sdir) <= AGULHAS["max_opposition_deg"])
                flags.append({
                    "type": "abnormal_waves", "level": "likely" if opposing else "watch",
                    "reason": f"SW swell from {sdir}° with sea {hs} m" + (f" against {ckmh} km/h current" if opposing else ""),
                })
    return flags


def _hour_as_day(hourly: dict, i: int) -> dict:
    def at(name):
        s = hourly.get(name) or []
        return s[i] if i < len(s) else None

    return {
        "wind_max": at("wind_speed_10m"), "gust_max": at("wind_gusts_10m"), "hs_max": at("wave_height"),
        "swell_max": at("swell_wave_height"), "swell_period_at_peak": at("swell_wave_period"),
        "swell_dir_at_peak": at("swell_wave_direction"), "current_dir_at_peak": at("ocean_current_direction"),
        "current_kmh_at_peak": at("ocean_current_velocity"),
    }


def window_label(start_utc: datetime, end_utc: datetime) -> str:
    """'Mon 5 Oct 10:00–19:00' in UK local time; spans days as 'Sun 4 Oct 22:00 – Mon 5 Oct 06:00'."""
    s, e = start_utc.astimezone(UK_TZ), end_utc.astimezone(UK_TZ)
    day = lambda d: f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"  # noqa: E731
    if s.date() == e.date():
        return f"{day(s)} {s:%H:%M}–{e:%H:%M}"
    return f"{day(s)} {s:%H:%M} – {day(e)} {e:%H:%M}"


def short_window_label(start_utc: datetime, end_utc: datetime) -> str:
    """'Mon 12:00–21:00' or 'Sat 14:00–Sun 01:00' (UK time) for narrow table columns."""
    s, e = start_utc.astimezone(UK_TZ), end_utc.astimezone(UK_TZ)
    if s.date() == e.date():
        return f"{s:%a %H:%M}–{e:%H:%M}"
    return f"{s:%a %H:%M}–{e:%a %H:%M}"


def exceedance_windows(loc: dict, hourly: dict, now: datetime | None = None) -> list[dict]:
    """Contiguous future hours where a port's operational thresholds are exceeded."""
    times = hourly.get("time") or []
    flagged = []
    for i, t in enumerate(times):
        ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        if now and ts < now.replace(minute=0, second=0, microsecond=0):
            continue
        flags = day_flags(loc, _hour_as_day(hourly, i))
        if flags:
            flagged.append((ts, i, flags))

    windows, current = [], None
    for ts, i, flags in flagged:
        if current and (ts - current["end"]) <= timedelta(hours=WINDOW_MERGE_GAP_H):
            current["end"] = ts
            current["idx"].append(i)
            current["flags"] += flags
        else:
            current = {"start": ts, "end": ts, "idx": [i], "flags": list(flags)}
            windows.append(current)

    out = []
    for w in windows:
        end = w["end"] + timedelta(hours=1)  # the flagged hour runs to the next hour
        gusts = [hourly["wind_gusts_10m"][i] for i in w["idx"] if hourly.get("wind_gusts_10m") and hourly["wind_gusts_10m"][i] is not None]
        seas = [hourly["wave_height"][i] for i in w["idx"] if hourly.get("wave_height") and hourly["wave_height"][i] is not None]
        out.append({
            "start": w["start"].strftime("%Y-%m-%dT%H:%MZ"),
            "end": end.strftime("%Y-%m-%dT%H:%MZ"),
            "label": window_label(w["start"], end),
            "short": short_window_label(w["start"], end),
            "hours": len(w["idx"]),
            "level": LEVEL_NAMES[worst(w["flags"])],
            "causes": sorted({f["type"] for f in w["flags"]}),
            "peak_gust": _round(max(gusts)) if gusts else None,
            "peak_sea": _round(max(seas), 1) if seas else None,
        })
    return out


def worst(flags: list[dict]) -> int:
    return max((LEVELS[f["level"]] for f in flags), default=0)


def assess_location(loc: dict, hourly: dict, storms: list[dict], now: datetime | None = None) -> dict:
    days = daily_peaks(hourly, now)
    for d in days:
        d["flags"] = day_flags(loc, d)
        d["level"] = LEVEL_NAMES[worst(d["flags"])]

    storm_flags = []
    for s in storms:
        for n in s.get("nearby", []):
            if n["id"] == loc["id"]:
                storm_flags.append({"type": "cyclone", "level": n["level"],
                                    "reason": f"{s['name']} ({s.get('severity') or s.get('alert_level')}) {n['distance_km']} km away"})

    def lvl(idx):
        return max((LEVELS[days[i]["level"]] for i in idx if i < len(days)), default=0)

    near = max(lvl([0, 1]), worst(storm_flags))
    ahead = lvl([3, 4, 5])
    trend = "deteriorating" if ahead > near else "improving" if ahead < near else "stable"
    # Headline day: the worst of D3-D5 if anything is flagged there, otherwise the worst of D0-D5.
    window = days[3:6] if ahead else days[:6]
    peak = max(window or days, key=lambda d: (LEVELS[d["level"]], d["gust_max"] or 0, d["hs_max"] or 0), default=None)

    return {
        "id": loc["id"],
        "name": loc["name"],
        "kind": loc["kind"],
        "region": loc["region"],
        "days": days,
        "storm_flags": storm_flags,
        "near_level": LEVEL_NAMES[near],
        "outlook_3_5d": LEVEL_NAMES[ahead],
        "trend": trend,
        "peak_day": peak["date"] if peak else None,
        "peak": {k: peak[k] for k in ("gust_max", "wind_max", "hs_max", "swell_max", "swell_period_at_peak")} if peak else None,
        "peak_flags": peak["flags"] if peak else [],
        "windows": exceedance_windows(loc, hourly, now) if loc["kind"] == "port" else [],
    }


def forecast_drift(current: dict, previous: dict | None, prev_run_id: str | None) -> list[dict]:
    """How the forecast for the same target days moved since the previous run."""
    if not previous:
        return []
    drifts = []
    for loc_id, cur in current.items():
        prev_days = {d["date"]: d for d in daily_peaks(previous.get(loc_id, {}))}
        for d in cur["days"][1:6]:
            p = prev_days.get(d["date"])
            if not p:
                continue
            dg = _delta(d["gust_max"], p["gust_max"])
            dh = _delta(d["hs_max"], p["hs_max"])
            if (dg is not None and abs(dg) >= DRIFT_GUST_MS) or (dh is not None and abs(dh) >= DRIFT_HS_M):
                drifts.append({
                    "id": loc_id, "name": cur["name"], "date": d["date"],
                    "gust_now": d["gust_max"], "gust_prev": p["gust_max"], "gust_delta": dg,
                    "hs_now": d["hs_max"], "hs_prev": p["hs_max"], "hs_delta": dh,
                    "since_run": prev_run_id,
                })
    return sorted(drifts, key=lambda x: -max(abs(x["gust_delta"] or 0) / DRIFT_GUST_MS, abs(x["hs_delta"] or 0) / DRIFT_HS_M))


def _delta(a, b):
    return round(a - b, 1) if a is not None and b is not None else None


def watchlist(assessments: list[dict], limit: int = 8) -> list[dict]:
    items = []
    for a in assessments:
        ahead, near = LEVELS[a["outlook_3_5d"]], LEVELS[a["near_level"]]
        top = max(ahead, near)
        if top == 0:
            continue
        score = (top * 10 + (4 if a["trend"] == "deteriorating" else 0)) * RELEVANCE[a["region"]]
        score += len(a["storm_flags"]) * 5
        items.append({
            "id": a["id"], "name": a["name"], "kind": a["kind"], "region": a["region"],
            "level": LEVEL_NAMES[top], "trend": a["trend"], "peak_day": a["peak_day"], "peak": a["peak"],
            "causes": sorted({f["type"] for f in a["peak_flags"] + a["storm_flags"]}),
            "reasons": [f["reason"] for f in (a["peak_flags"] + a["storm_flags"])][:3],
            "score": round(score, 1),
        })
    return sorted(items, key=lambda i: -i["score"])[:limit]


def previous_weather(run_id: str) -> tuple[dict | None, str | None]:
    files = sorted(f for f in paths.WEATHER_HISTORY.glob("*.json") if f.stem < run_id)
    if not files:
        return None, None
    prev = json.loads(files[-1].read_text())
    return prev.get("hourly"), prev.get("run_id")


def congestion_context(snapshot: dict) -> dict:
    """Compare today's Sinay occupancy with our own trailing history."""
    sc = snapshot["sources"].get("sinay_congestion", {})
    ports = (sc.get("data") or {}).get("ports") or {}
    history = sorted(paths.CONGESTION_HISTORY.glob("*.json"))[-16:]
    past: dict[str, list[float]] = defaultdict(list)
    past_tip: dict[str, list[float]] = defaultdict(list)
    for f in history:
        rec = json.loads(f.read_text())
        if rec.get("run_id") == snapshot["run_id"]:
            continue
        for pid, v in rec.get("ports", {}).items():
            if v.get("occupancy_pct") is not None:
                past[pid].append(v["occupancy_pct"])
            if v.get("time_in_port_median_h") is not None:
                past_tip[pid].append(v["time_in_port_median_h"])
    out = {}
    for pid, v in ports.items():
        trailing = past.get(pid)
        avg = round(sum(trailing) / len(trailing), 1) if trailing else None
        out[pid] = {**v, "name": BY_ID[pid]["name"], "trailing_avg_pct": avg,
                    "vs_trailing_pp": _delta(v.get("occupancy_pct"), avg), "history_runs": len(trailing or []),
                    "time_in_port_trailing_avg_h": round(sum(past_tip[pid]) / len(past_tip[pid]), 1) if past_tip.get(pid) else None}
    return out


def judge(snapshot: dict) -> dict:
    mw = snapshot["sources"].get("marine_weather", {})
    hist_file = (mw.get("data") or {}).get("history_file")
    hourly = json.loads((paths.ROOT / hist_file).read_text())["hourly"] if hist_file else {}
    storms = (snapshot["sources"].get("cyclones", {}).get("data") or {}).get("storms", [])

    generated = datetime.strptime(snapshot["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assessments = {}
    for loc in LOCATIONS:
        if loc["id"] in hourly and hourly[loc["id"]].get("time"):
            assessments[loc["id"]] = assess_location(loc, hourly[loc["id"]], storms, now=generated)

    prev_hourly, prev_run = previous_weather(snapshot["run_id"])

    congestion = congestion_context(snapshot)
    judgement = {
        "question": "Which ports and lanes are likely to deteriorate in the next three to five days?",
        "levels": list(LEVELS),
        "locations": assessments,
        "watchlist": watchlist(list(assessments.values())),
        "deteriorating": [a["id"] for a in assessments.values() if a["trend"] == "deteriorating"],
        "forecast_drift": forecast_drift(assessments, prev_hourly, prev_run)[:10],
        "congestion": congestion,
        "ports_status": port_status.ports_status(snapshot, assessments, congestion),
        "inbound": port_status.inbound(assessments),
        "storms": storms,
        "forecast_issued": snapshot["generated_at"],
    }
    snapshot["judgement"] = judgement
    return judgement
