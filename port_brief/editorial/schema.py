"""The editorial contract between the data and the words.

Claude (in the routine) or the templated fallback writes drafts/<date>/editorial.json.
Every figure in the prose must be traceable to the snapshot: the validator extracts each
number from the text and rejects any that no snapshot value rounds to.
"""

from __future__ import annotations

import re
from datetime import date

from port_brief.config import playbook as pb
from port_brief.config.locations import LANE_THRESHOLDS, PORT_THRESHOLDS

LIMITS = {"headline": 90, "standfirst": 340, "watchlist_note": 220, "section": 1100, "port_note": 260, "inbound_note": 600}
SECTIONS = ("ports", "lanes", "reliability", "advisories")
ALWAYS_ALLOWED = set(range(0, 14))  # counts, "three to five days", "top 13", "D5"

NUMBER_RE = re.compile(r"(?<![A-Za-z\d.])-?\d+(?:\.\d+)?")
# A number followed (possibly via a range like "5–7") by a unit is a quantity, never a bare count.
UNIT_AFTER_RE = re.compile(r"(?:\s*[–-]\s*\d+(?:\.\d+)?)*\s*(?:days?|hours?|hrs?|h\b|weeks?|pp\b|%|m/s|m\b|km\b|knots?|kn\b)", re.I)


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
    _numbers_in([pb.BUFFER, pb.INBOUND_DELAY, pb.CONGESTED_GAP_PP, pb.BUSY_GAP_PP, pb.CONGESTED_TIME_IN_PORT_PCT], vals)
    _numbers_in(issue_date, vals)
    return sorted({abs(v) for v in vals})


def unsupported_numbers(text: str, allowed: list[float]) -> list[str]:
    """Numbers no data value rounds to. Small bare counts ("three", "top 13") are fine, but any
    number carrying a unit (days, hours, %, pp, m/s...) must come from the data or the playbook."""
    bad = []
    text = text.replace(",", "")
    for m in NUMBER_RE.finditer(text):
        token = m.group()
        t = abs(float(token))
        decimals = len(token.split(".")[1]) if "." in token else 0
        tol = 0.5 * 10 ** -decimals + 1e-9
        if any(abs(a - t) <= tol for a in allowed):
            continue
        if t in ALWAYS_ALLOWED and not UNIT_AFTER_RE.match(text, m.end()):
            continue
        bad.append(token)
    return bad


def validate(editorial: dict, snapshot: dict, issue_date: str) -> list[str]:
    errors = []
    editorial.setdefault("watchlist_notes", {})
    for key in ("headline", "standfirst", "sections", "author", "port_notes", "inbound_note"):
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

    port_ids = [p["id"] for p in snapshot.get("judgement", {}).get("ports_status", [])]
    for pid in port_ids:
        check_len(f"port_notes.{pid}", editorial["port_notes"].get(pid, ""), LIMITS["port_note"])
    for pid in editorial["port_notes"]:
        if pid not in port_ids:
            errors.append(f"port_notes.{pid}: not a tracked port")
    if not isinstance(editorial["inbound_note"], str) or len(editorial["inbound_note"]) > LIMITS["inbound_note"]:
        errors.append(f"inbound_note: must be text of at most {LIMITS['inbound_note']} chars")

    picks = editorial.get("advisory_picks")
    if picks is not None:
        known = {i["url"] for p in snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {}).values() for i in p["items"]}
        for url in picks:
            if url not in known:
                errors.append(f"advisory_picks: unknown url {url[:80]}")

    allowed = allowed_numbers(snapshot, issue_date)
    texts = {"headline": editorial["headline"], "standfirst": editorial["standfirst"],
             **{f"sections.{k}": v for k, v in editorial["sections"].items()},
             **{f"watchlist_notes.{k}": v for k, v in editorial["watchlist_notes"].items()},
             **{f"port_notes.{k}": v for k, v in editorial["port_notes"].items()},
             "inbound_note": editorial["inbound_note"]}
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


def _clip(text: str, limit: int) -> str:
    """Trim to the limit at a sentence boundary where possible."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > limit // 2 else cut[: limit - 1].rstrip() + "…"


def fallback(snapshot: dict, issue_date: str) -> dict:
    j = snapshot.get("judgement", {})
    wl = j.get("watchlist", [])
    rel = snapshot["sources"].get("schedule_reliability", {}).get("data", {})
    si, xe, dv = rel.get("sea_intelligence"), rel.get("xeneta"), rel.get("divergence")

    statuses = j.get("ports_status", [])
    flagged = [p for p in statuses if p["status"] != "normal"]
    worst = max(flagged, key=lambda p: pb.STATUS_ORDER.index(p["status"]), default=None)
    if worst:
        headline = f"{worst['name']}: {worst['status_label'].lower()}"
        if worst["windows"]:
            headline += f" {worst['windows'][0]['label']}"
        if len(flagged) > 1:
            headline += f"; {len(flagged) - 1} more port{'s' if len(flagged) > 2 else ''} to watch"
    elif statuses and any(p["data_gaps"] for p in statuses):
        headline = "No weather disruption forecast at UK and North European ports this week"
    elif statuses:
        headline = "All UK and North European ports running normally this week"
    else:
        headline = "Port Brief"
    headline = headline[: LIMITS["headline"]]

    stand = []
    if flagged:
        stand.append("Action needed at " + ", ".join(f"{p['name']} ({p['status_label'].lower()})" for p in flagged[:4]) + ".")
    elif statuses:
        stand.append("No weather disruption forecast at the UK and North European ports we track. Good week to push releases and deliveries.")
    inbound = j.get("inbound", [])
    if inbound:
        stand.append(f"Inbound: weather may delay {inbound[0]['trades']} by {inbound[0]['delay']}.")
    if si and si.get("global_pct") is not None:
        stand.append(f"Reliability: Sea-Intelligence {si['global_pct']}%"
                     + (f", Xeneta {xe['global_pct']}%." if xe and xe.get("global_pct") is not None else "."))
    standfirst = " ".join(stand)
    if len(standfirst) > LIMITS["standfirst"]:
        standfirst = " ".join(stand[:-1])[: LIMITS["standfirst"]]

    port_notes = {}
    for p in statuses:
        action = " ".join(p["actions"])
        note = f"{p['reasons'][0][0].upper()}{p['reasons'][0][1:]}. {action}" if p["reasons"] else action
        if len(note) > LIMITS["port_note"]:
            note = p["actions"][0]
        port_notes[p["id"]] = _clip(note, LIMITS["port_note"])

    inbound_note = (" ".join(f"{i['name']}: {i['action']}" for i in inbound[:2]) if inbound
                    else "No weather on the main routes into the UK and North Europe is expected to delay arrivals this week.")
    inbound_note = _clip(inbound_note, LIMITS["inbound_note"])

    notes = {}
    for w in wl:
        reasons = "; ".join(w["reasons"][:2])
        notes[w["id"]] = (f"{w['level'].capitalize()} risk of {_causes(w)} {day_label(w['peak_day'])}"
                          f" ({reasons}). Trend: {w['trend']}.")[: LIMITS["watchlist_note"]]

    if flagged:
        port_txt = " ".join(f"{p['name']}: {p['status_label'].lower()}." for p in flagged)
        port_txt += f" {len(statuses) - len(flagged)} of {len(statuses)} ports are running normally."
    else:
        port_txt = "All the ports we track are running normally, with no crane or pilotage limits forecast."
    if any(p["data_gaps"] for p in statuses):
        port_txt += " Congestion data was unavailable for this issue, so statuses reflect weather and port news only."

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
        "port_notes": port_notes,
        "inbound_note": inbound_note,
        "sections": {"ports": port_txt[: LIMITS["section"]], "lanes": lane_txt[: LIMITS["section"]],
                     "reliability": rel_txt[: LIMITS["section"]], "advisories": adv_txt},
    }
