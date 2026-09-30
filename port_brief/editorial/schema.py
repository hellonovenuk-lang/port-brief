"""The editorial contract between the data and the words.

Claude (in the routine) or the templated fallback writes drafts/<date>/editorial.json.
Every figure in the prose must be traceable to the snapshot: the validator extracts each
number from the text and rejects any that no snapshot value rounds to.
"""

from __future__ import annotations

import re
from datetime import date

from port_brief.config.locations import LANE_THRESHOLDS, PORT_THRESHOLDS

LIMITS = {"headline": 90, "standfirst": 340, "watchlist_note": 220, "section": 1100}
SECTIONS = ("ports", "lanes", "reliability", "advisories")
ALWAYS_ALLOWED = set(range(0, 14))  # counts, "three to five days", "top 13", "D5"

NUMBER_RE = re.compile(r"(?<![A-Za-z\d.])-?\d+(?:\.\d+)?")


def _numbers_in(obj, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, str):
        # Dates (2026-10-03), headline figures ("USD 500"), period labels.
        for m in re.findall(r"\d+(?:\.\d+)?", obj.replace(",", "")):
            out.append(float(m))


def allowed_numbers(snapshot: dict, issue_date: str) -> list[float]:
    vals: list[float] = []
    _numbers_in(snapshot.get("judgement", {}), vals)
    rel = snapshot["sources"].get("schedule_reliability", {}).get("data", {})
    _numbers_in({k: v for k, v in rel.items() if k != "xeneta_pending"}, vals)
    for s in ("sinay_congestion", "cyclones"):
        _numbers_in(snapshot["sources"].get(s, {}).get("data", {}), vals)
    for pub in snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {}).values():
        _numbers_in([i["title"] for i in pub["items"]], vals)
    _numbers_in([PORT_THRESHOLDS, LANE_THRESHOLDS], vals)
    _numbers_in(issue_date, vals)
    return sorted({abs(v) for v in vals} | {float(v) for v in ALWAYS_ALLOWED})


def unsupported_numbers(text: str, allowed: list[float]) -> list[str]:
    bad = []
    for token in NUMBER_RE.findall(text.replace(",", "")):
        t = abs(float(token))
        decimals = len(token.split(".")[1]) if "." in token else 0
        tol = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(a - t) <= tol for a in allowed):
            bad.append(token)
    return bad


def validate(editorial: dict, snapshot: dict, issue_date: str) -> list[str]:
    errors = []
    for key in ("headline", "standfirst", "watchlist_notes", "sections", "author"):
        if key not in editorial:
            errors.append(f"missing field: {key}")
    if errors:
        return errors

    def check_len(label, text, limit):
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}: empty")
        elif len(text) > limit:
            errors.append(f"{label}: {len(text)} chars (max {limit})")

    check_len("headline", editorial["headline"], LIMITS["headline"])
    check_len("standfirst", editorial["standfirst"], LIMITS["standfirst"])
    for s in SECTIONS:
        check_len(f"sections.{s}", editorial["sections"].get(s, ""), LIMITS["section"])

    watch_ids = {w["id"] for w in snapshot.get("judgement", {}).get("watchlist", [])}
    for loc_id, note in editorial["watchlist_notes"].items():
        if loc_id not in watch_ids:
            errors.append(f"watchlist_notes.{loc_id}: not on the watchlist")
        check_len(f"watchlist_notes.{loc_id}", note, LIMITS["watchlist_note"])

    picks = editorial.get("advisory_picks")
    if picks is not None:
        known = {i["url"] for p in snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {}).values() for i in p["items"]}
        for url in picks:
            if url not in known:
                errors.append(f"advisory_picks: unknown url {url[:80]}")

    allowed = allowed_numbers(snapshot, issue_date)
    texts = {"headline": editorial["headline"], "standfirst": editorial["standfirst"],
             **{f"sections.{k}": v for k, v in editorial["sections"].items()},
             **{f"watchlist_notes.{k}": v for k, v in editorial["watchlist_notes"].items()}}
    for label, text in texts.items():
        bad = unsupported_numbers(text or "", allowed)
        if bad:
            errors.append(f"{label}: numbers not found in the data: {', '.join(bad)}")
    return errors


# ------------------------------------------------------------------ templated fallback

def day_label(iso_day: str | None) -> str:
    if not iso_day:
        return "later this week"
    d = date.fromisoformat(iso_day)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


CAUSE_TEXT = {
    "crane": "crane stoppages", "pilot": "pilot boarding suspensions",
    "heavy_weather": "heavy weather", "abnormal_waves": "abnormal-wave risk", "cyclone": "a tropical cyclone",
}


def _causes(item) -> str:
    causes = [CAUSE_TEXT.get(c, c) for c in item["causes"]] or ["deteriorating conditions"]
    return " and ".join(causes)


def fallback(snapshot: dict, issue_date: str) -> dict:
    j = snapshot.get("judgement", {})
    wl = j.get("watchlist", [])
    rel = snapshot["sources"].get("schedule_reliability", {}).get("data", {})
    si, xe, dv = rel.get("sea_intelligence"), rel.get("xeneta"), rel.get("divergence")

    if wl:
        top = wl[0]
        headline = f"{top['name']}: {_causes(top)} risk {day_label(top['peak_day'])}"
    else:
        headline = "Quiet weather outlook across UK ports and key lanes"
    headline = headline[: LIMITS["headline"]]

    deteriorating = [j["locations"][i]["name"] for i in j.get("deteriorating", [])]
    stand = []
    if deteriorating:
        stand.append(f"Conditions worsen over the next three to five days at {', '.join(deteriorating[:4])}.")
    else:
        stand.append("No port or lane we track is forecast to deteriorate over the next three to five days.")
    if si and si.get("global_pct") is not None:
        stand.append(f"Sea-Intelligence puts global schedule reliability at {si['global_pct']}%")
        if xe and xe.get("global_pct") is not None:
            stand[-1] += f"; Xeneta measures {xe['global_pct']}%."
        else:
            stand[-1] += "."
    standfirst = " ".join(stand)[: LIMITS["standfirst"]]

    notes = {}
    for w in wl:
        reasons = "; ".join(w["reasons"][:2])
        notes[w["id"]] = (f"{w['level'].capitalize()} risk of {_causes(w)} {day_label(w['peak_day'])}"
                          f" ({reasons}). Trend: {w['trend']}.")[: LIMITS["watchlist_note"]]

    ports = [a for a in j.get("locations", {}).values() if a["kind"] == "port"]
    flagged_ports = [a for a in ports if a["outlook_3_5d"] != "none" or a["near_level"] != "none"]
    if flagged_ports:
        port_txt = "Ports with flagged days: " + "; ".join(
            f"{a['name']} ({a['outlook_3_5d'] if a['outlook_3_5d'] != 'none' else a['near_level']}, {day_label(a['peak_day'])})"
            for a in flagged_ports) + "."
    else:
        port_txt = "No crane or pilotage thresholds are forecast to be reached at the ports we track this week."
    cong = j.get("congestion") or {}
    if cong:
        busiest = max(cong.values(), key=lambda c: c.get("occupancy_pct") or 0)
        port_txt += f" Highest berth occupancy: {busiest['name']} at {busiest['occupancy_pct']}%."

    lanes = [a for a in j.get("locations", {}).values() if a["kind"] == "lane"]
    flagged_lanes = [a for a in lanes if a["outlook_3_5d"] != "none" or a["near_level"] != "none"]
    lane_txt = ("Lanes with flagged days: " + "; ".join(
        f"{a['name']} ({day_label(a['peak_day'])})" for a in flagged_lanes) + "."
                ) if flagged_lanes else "No heavy-weather thresholds are forecast on the lanes we track."
    storms_near = [s for s in j.get("storms", []) if s.get("nearby")]
    if storms_near:
        lane_txt += " Tropical cyclones near tracked locations: " + ", ".join(s["name"] for s in storms_near) + "."

    if si and si.get("global_pct") is not None:
        rel_txt = f"Sea-Intelligence: {si['global_pct']}% on time in {si['period']}"
        if si.get("mom_pp") is not None:
            rel_txt += f" ({si['mom_pp']:+} pp month on month)"
        rel_txt += "."
        if xe and xe.get("global_pct") is not None:
            rel_txt += f" Xeneta: {xe['global_pct']}% for {xe['period']}."
        if dv and dv.get("comparable"):
            rel_txt += (f" The two benchmarks sit {abs(dv['global_gap_pp'])} pp apart because they define 'on time' differently;"
                        " read them as two views of the same trend, not as a contradiction.")
    else:
        rel_txt = "Schedule reliability figures were unavailable for this issue."

    adv_count = sum(len(p["items"]) for p in snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {}).values())
    adv_txt = ("Operational notices from the past week from the ports and carriers we follow. "
               "Items marked NEW did not appear in a previous issue."
               if adv_count else "No operational notices from the ports and carriers we follow this week.")

    return {
        "issue_date": issue_date,
        "author": "template",
        "headline": headline,
        "standfirst": standfirst,
        "watchlist_notes": notes,
        "sections": {"ports": port_txt[: LIMITS["section"]], "lanes": lane_txt[: LIMITS["section"]],
                     "reliability": rel_txt[: LIMITS["section"]], "advisories": adv_txt},
    }
