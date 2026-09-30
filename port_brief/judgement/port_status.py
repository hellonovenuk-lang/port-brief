"""One status and one set of actions per port, for small importer teams.

Combines three signals, worst wins:
  weather  - exceedance windows from weather_risk (crane / pilot thresholds)
  congestion - Sinay occupancy vs the port's usual level, and time in port vs our history
  port news  - disruption or congestion headlines naming the port in the past week
All wording and buffers come from config/playbook.py.
"""

from __future__ import annotations

from port_brief.config import playbook as pb
from port_brief.config.locations import BY_ID, LOCATIONS, PORTS


def _rank(status: str) -> int:
    return pb.STATUS_ORDER.index(status)


def port_headlines(snapshot: dict, port: dict) -> list[dict]:
    """Advisory items (any publisher) whose headline names this port."""
    aliases = [a.lower() for a in port.get("aliases", [port["name"]])]
    found, seen = [], set()
    pubs = snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {})
    for p in pubs.values():
        for item in p["items"]:
            title = item["title"].lower()
            if item["url"] in seen or not any(a in title for a in aliases):
                continue
            if any(x in title for x in pb.HEADLINE_EXCLUDE):
                continue
            seen.add(item["url"])
            kind = ("disruption" if any(k in title for k in pb.DISRUPTION_KEYWORDS)
                    else "congestion" if any(k in title for k in pb.CONGESTION_KEYWORDS) else None)
            if kind:
                found.append({**item, "signal": kind})
    return found


def congestion_signal(c: dict | None) -> tuple[str | None, str | None]:
    """(status, reason) from Sinay data; (None, None) when there is no data."""
    if not c or c.get("occupancy_pct") is None:
        return None, None
    gap = c.get("occupancy_gap_vs_mean_pct")
    tip = c.get("time_in_port_median_h")
    tip_avg = c.get("time_in_port_trailing_avg_h")
    tip_pct = round((tip - tip_avg) / tip_avg * 100) if tip is not None and tip_avg else None
    if (gap is not None and gap >= pb.CONGESTED_GAP_PP) or (tip_pct is not None and tip_pct >= pb.CONGESTED_TIME_IN_PORT_PCT):
        bits = []
        if gap is not None and gap >= pb.CONGESTED_GAP_PP:
            bits.append(f"berth occupancy {c['occupancy_pct']:.0f}%, {gap:+.0f} pp above normal")
        if tip_pct is not None and tip_pct >= pb.CONGESTED_TIME_IN_PORT_PCT:
            bits.append(f"ships spending {tip_pct}% longer in port than usual")
        return "congested", "; ".join(bits)
    if gap is not None and gap >= pb.BUSY_GAP_PP:
        return "watch", f"berth occupancy {c['occupancy_pct']:.0f}%, {gap:+.0f} pp above normal"
    return "normal", f"berth occupancy {c['occupancy_pct']:.0f}%" + (f" ({gap:+.0f} pp vs normal)" if gap is not None else "")


def assess_port(port: dict, assessment: dict | None, congestion: dict | None, headlines: list[dict]) -> dict:
    status, reasons, actions, gaps = "normal", [], [], []
    windows = (assessment or {}).get("windows", [])

    likely = [w for w in windows if w["level"] == "likely"]
    watch = [w for w in windows if w["level"] == "watch"]
    if likely:
        w = likely[0]
        status = "disruption"
        reasons.append(f"{' and '.join('crane' if c == 'crane' else 'pilotage' for c in w['causes'])} limits exceeded "
                       f"{w['label']}" + (f", gusts to {w['peak_gust']:.0f} m/s" if w.get("peak_gust") else ""))
        actions.append(pb.ACTIONS["disruption_weather"].format(window=w["label"]))
    elif watch:
        w = watch[0]
        status = "watch"
        reasons.append(f"near {' and '.join('crane' if c == 'crane' else 'pilotage' for c in w['causes'])} limits "
                       f"{w['label']}" + (f", gusts to {w['peak_gust']:.0f} m/s" if w.get("peak_gust") else ""))
        actions.append(pb.ACTIONS["watch_weather"].format(window=w["label"]))

    c_status, c_reason = congestion_signal(congestion)
    if c_status is None:
        gaps.append(pb.NO_CONGESTION_DATA)
    else:
        if c_status in ("congested", "watch") and c_reason:
            reasons.append(c_reason)
        if c_status == "congested":
            actions.append(pb.ACTIONS["congested"])
        elif c_status == "watch" and not windows:
            actions.append(pb.ACTIONS["watch_busy"])
        if _rank(c_status) > _rank(status):
            status = c_status

    for h in headlines:
        if h["signal"] == "disruption":
            reasons.append(f"reported: {h['title']}")
            actions.append(pb.ACTIONS["disruption_news"].format(headline=h["title"]))
            status = "disruption"
            break
        if h["signal"] == "congestion" and _rank(status) < _rank("watch"):
            reasons.append(f"reported: {h['title']}")
            actions.append(pb.ACTIONS["watch_news"].format(headline=h["title"]))
            status = "watch"

    if status == "normal":
        actions = [pb.ACTIONS["normal"] if c_status else pb.ACTIONS["normal_no_congestion"]]

    return {
        "id": port["id"],
        "name": port["name"],
        "region": port["region"],
        "status": status,
        "status_label": pb.STATUS_LABEL[status],
        "reasons": reasons,
        "actions": actions,
        "windows": windows,
        "congestion": congestion,
        "headlines": headlines[:2],
        "data_gaps": gaps,
    }


def ports_status(snapshot: dict, assessments: dict, congestion: dict) -> list[dict]:
    return [assess_port(p, assessments.get(p["id"]), congestion.get(p["id"]), port_headlines(snapshot, p)) for p in PORTS]


def inbound(assessments: dict) -> list[dict]:
    """Lanes where weather is likely to delay ships heading to UK / North European ports."""
    out = []
    for loc in LOCATIONS:
        a = assessments.get(loc["id"])
        if loc["kind"] != "lane" or not a:
            continue
        levels = [d["level"] for d in a["days"]]
        worst = "likely" if "likely" in levels else "watch" if "watch" in levels else "none"
        if worst == "none" and not a["storm_flags"]:
            continue
        worst = "likely" if any(f["level"] == "likely" for f in a["storm_flags"]) else (worst if worst != "none" else "watch")
        flagged_days = [d for d in a["days"] if d["level"] != "none"]
        delay = pb.INBOUND_DELAY[worst]
        out.append({
            "id": loc["id"],
            "name": loc["name"],
            "trades": loc.get("inbound_trades", ""),
            "level": worst,
            "from_day": flagged_days[0]["date"] if flagged_days else None,
            "to_day": flagged_days[-1]["date"] if flagged_days else None,
            "peak_sea": max((d["hs_max"] or 0 for d in flagged_days), default=None),
            "peak_wind": max((d["wind_max"] or 0 for d in flagged_days), default=None),
            "storm": a["storm_flags"][0]["reason"] if a["storm_flags"] else None,
            "delay": delay,
            "action": f"Expect {loc.get('inbound_trades', 'affected services')} to run {delay} late. "
                      "Don't book haulage against the published ETA; confirm the revised ETA with your carrier.",
        })
    order = {"likely": 0, "watch": 1}
    return sorted(out, key=lambda x: (order[x["level"]], BY_ID[x["id"]]["region"] != "uk"))
