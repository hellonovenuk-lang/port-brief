"""The editorial contract between the data and the words.

Claude (in the routine) or the templated fallback writes drafts/<date>/editorial.json.
Every figure in the prose must be traceable to the snapshot: the validator extracts each
number from the text and rejects any that no snapshot value rounds to.
"""

from __future__ import annotations

import re
from datetime import date

from port_brief.config import playbook as pb
from port_brief.editorial import slop
from port_brief.config.locations import LANE_THRESHOLDS, PORT_THRESHOLDS

# Short by design: the issue is read at a glance, so every field has a tight limit.
LIMITS = {"headline": 80, "summary_line": 110, "port_note": 90, "inbound_note": 160,
          "advisories": 300, "reliability": 200}
SUMMARY_PARTS = ("ports", "weather", "news")
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
    _numbers_in([pb.BUFFER, pb.INBOUND_DELAY, pb.SEVERITY_SEA_M, pb.CONGESTED_GAP_PP, pb.BUSY_GAP_PP, pb.CONGESTED_TIME_IN_PORT_PCT], vals)
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


def style_issues(text: str) -> list[str]:
    """Writing tics that read as machine-made. Rules live in editorial/slop.py and STYLE.md."""
    return slop.text_issues(text)


def validate(editorial: dict, snapshot: dict, issue_date: str) -> list[str]:
    errors = []
    for key in ("headline", "summary", "port_notes", "inbound_note", "sections", "author"):
        if key not in editorial:
            errors.append(f"missing field: {key}")
    if errors:
        return errors

    def check_len(label, text, limit, allow_empty=False):
        if not isinstance(text, str) or (not allow_empty and not text.strip()):
            errors.append(f"{label}: empty")
        elif len(text) > limit:
            errors.append(f"{label}: {len(text)} chars (max {limit})")

    check_len("headline", editorial["headline"], LIMITS["headline"])
    for part in SUMMARY_PARTS:
        check_len(f"summary.{part}", editorial["summary"].get(part, ""), LIMITS["summary_line"])
    check_len("inbound_note", editorial["inbound_note"], LIMITS["inbound_note"])
    check_len("sections.advisories", editorial["sections"].get("advisories", ""), LIMITS["advisories"], allow_empty=True)
    check_len("sections.reliability", editorial["sections"].get("reliability", ""), LIMITS["reliability"], allow_empty=True)

    port_ids = [p["id"] for p in snapshot.get("judgement", {}).get("ports_status", [])]
    for pid in port_ids:
        check_len(f"port_notes.{pid}", editorial["port_notes"].get(pid, ""), LIMITS["port_note"])
    for pid in editorial["port_notes"]:
        if pid not in port_ids:
            errors.append(f"port_notes.{pid}: not a tracked port")

    picks = editorial.get("advisory_picks")
    if picks is not None:
        known = {i["url"] for p in snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {}).values() for i in p["items"]}
        for url in picks:
            if url not in known:
                errors.append(f"advisory_picks: unknown url {url[:80]}")

    errors += slop.notes_issues(editorial["port_notes"])

    allowed = allowed_numbers(snapshot, issue_date)
    texts = {"headline": editorial["headline"],
             **{f"summary.{k}": v for k, v in editorial["summary"].items()},
             **{f"sections.{k}": v for k, v in editorial["sections"].items()},
             **{f"port_notes.{k}": v for k, v in editorial["port_notes"].items()},
             "inbound_note": editorial["inbound_note"]}
    for label, text in texts.items():
        bad = unsupported_numbers(text or "", allowed)
        if bad:
            errors.append(f"{label}: numbers not found in the data: {', '.join(bad)}")
        for issue in style_issues(text or ""):
            errors.append(f"{label}: {issue}")
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


def _period(p: str) -> str:
    y, m = p.split("-", 1)
    return f"{m} {y}" if m.startswith("Q") else f"{date(int(y), int(m), 1):%B %Y}"


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _clip(text: str, limit: int) -> str:
    """Trim to the limit at a sentence boundary where possible."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > limit // 2 else cut[: limit - 1].rstrip() + "…"


def fallback(snapshot: dict, issue_date: str) -> dict:
    """Short, data-only wording straight from the playbook, so every issue is complete."""
    j = snapshot.get("judgement", {})
    statuses = j.get("ports_status", [])
    by_status = {k: [p["name"] for p in statuses if p["status"] == k] for k in pb.STATUS_ORDER}
    routes = j.get("routes", [])
    rough_routes = [r for r in routes if r["level"] != "none"]
    worst_route = max(rough_routes, key=lambda r: ["watch", "likely", "extreme"].index(r["level"]), default=None)

    # Summary: one line per part.
    flagged = [(k, by_status[k]) for k in ("disruption", "congested", "watch") if by_status[k]]
    if flagged:
        worst_status, worst_names = flagged[0]
        ports_line = f"{pb.STATUS_LABEL[worst_status]} at {_join(worst_names)}."
        others = sum(len(names) for _, names in flagged[1:])
        if others:
            ports_line += f" {others} more port{'s' if others > 1 else ''} to watch."
    else:
        ports_line = ("All eight ports are running normally." if not any(p["data_gaps"] for p in statuses)
                      else "No weather disruption is forecast at any of the eight ports.")
    if worst_route:
        weather_line = f"{worst_route['severity']} seas put {worst_route['name']} arrivals {worst_route['delay']} late."
        if len(rough_routes) > 1:
            weather_line += f" {len(rough_routes) - 1} more route{'s' if len(rough_routes) > 2 else ''} affected."
    else:
        weather_line = "No weather delays on the routes into the UK."
    adv = snapshot["sources"].get("advisories", {}).get("data", {}).get("publishers", {})
    n_items = sum(len(p["items"]) for p in adv.values())
    news_line = f"{n_items} notices from ports and shipping lines this week." if n_items else "No new notices from ports or shipping lines."

    if by_status["disruption"]:
        headline = f"Disruption likely at {_join(by_status['disruption'])}"
    elif by_status["congested"]:
        headline = f"{_join(by_status['congested'])} busier than normal"
    elif worst_route and worst_route["level"] in ("likely", "extreme"):
        headline = f"{worst_route['severity']} seas slow {worst_route['name']} arrivals"
    elif by_status["watch"]:
        headline = f"Gusty spells at {len(by_status['watch'])} of {len(statuses)} ports this week"
    else:
        headline = "A quiet week at UK and North European ports"

    port_notes = {p["id"]: _clip(p.get("short_action") or p["actions"][0], LIMITS["port_note"]) for p in statuses}
    inbound_note = (f"Worst this week: {worst_route['name']}, {worst_route['delay']}. Confirm revised ETAs before booking haulage."
                    if worst_route else "No weather on the routes into the UK is expected to delay arrivals.")

    rel = snapshot["sources"].get("schedule_reliability", {}).get("data", {})
    si, xe = rel.get("sea_intelligence"), rel.get("xeneta")
    rel_txt = ""
    if si and si.get("global_pct") is not None:
        rel_txt = f"On time in {_period(si['period'])}: Sea-Intelligence {si['global_pct']}%"
        if xe and xe.get("global_pct") is not None:
            rel_txt += f" and Xeneta {xe['global_pct']}%, which uses a stricter measure"
        rel_txt += "."

    return {
        "issue_date": issue_date,
        "author": "template",
        "headline": _clip(headline, LIMITS["headline"]),
        "summary": {"ports": _clip(ports_line, LIMITS["summary_line"]), "weather": _clip(weather_line, LIMITS["summary_line"]),
                    "news": _clip(news_line, LIMITS["summary_line"])},
        "port_notes": port_notes,
        "inbound_note": _clip(inbound_note, LIMITS["inbound_note"]),
        "sections": {"advisories": "", "reliability": _clip(rel_txt, LIMITS["reliability"])},
    }
