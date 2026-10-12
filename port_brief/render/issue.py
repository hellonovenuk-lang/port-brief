"""Render an issue to PDF (WeasyPrint), subscriber email HTML/text, and a page-1 preview PNG."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from port_brief.config import playbook as pb
from port_brief.config.locations import BY_ID, LANE_THRESHOLDS, LOCATIONS, PORT_THRESHOLDS
from port_brief.editorial.schema import CAUSE_TEXT, day_label
from port_brief.render import charts, worldmap

TEMPLATES = Path(__file__).parent / "templates"
HEALTH_NAMES = {"marine_weather": "weather", "cyclones": "tropical storms", "sinay_congestion": "congestion",
                "schedule_reliability": "schedule reliability", "advisories": "notices"}
HEALTH_WORDS = {"ok": "complete", "partial": "partly available", "failed": "unavailable",
                "skipped": "not connected", "stale": "last published figures"}
UNCURATED_PER_PUBLISHER = 3
REGION_ORDER = {"uk": 0, "north_europe": 1, "global": 2}


PORT_IDS = {loc["id"] for loc in LOCATIONS if loc["kind"] == "port"}


def _crosses_limit(d: dict) -> bool:
    """A lane forecast change only matters if it moves the sea state across the Rough line."""
    rough = pb.SEVERITY_SEA_M["watch"]
    return d.get("hs_prev") is not None and d.get("hs_now") is not None and (d["hs_prev"] >= rough) != (d["hs_now"] >= rough)


def period_label(p: str | None) -> str:
    if not p:
        return ""
    y, rest = p.split("-", 1)
    return f"{rest} {y}" if rest.startswith("Q") else f"{date(int(y), int(rest), 1):%b %Y}"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False))
    env.filters["day"] = day_label
    env.filters["short_day"] = lambda d: date.fromisoformat(d).strftime("%a") if d else ""
    env.filters["cause"] = lambda c: CAUSE_TEXT.get(c, c)
    env.filters["pp"] = lambda v: "–" if v is None else f"{v:+.1f} pp"
    env.filters["period"] = period_label
    env.filters["sentence"] = lambda t: (t[:1].upper() + t[1:]) if t else t
    env.filters["signed"] = lambda v: "–" if v is None else f"{v:+.0f}"
    env.filters["num"] = lambda v, nd=1: "–" if v is None else f"{v:.{nd}f}"
    return env


def context(snap: dict, editorial: dict, meta: dict) -> dict:
    j = snap["judgement"]
    rel = snap["sources"]["schedule_reliability"]["data"]
    config_order = {loc["id"]: i for i, loc in enumerate(LOCATIONS)}
    locs = sorted(j["locations"].values(), key=lambda a: (a["kind"] != "port", REGION_ORDER[a["region"]], config_order.get(a["id"], 99)))
    ports = [a for a in locs if a["kind"] == "port"]
    lanes = [a for a in locs if a["kind"] == "lane"]
    day_keys = [d["date"] for d in (ports or lanes)[0]["days"]] if locs else []

    advisories = snap["sources"]["advisories"]["data"]["publishers"]
    picks = editorial.get("advisory_picks")
    adv_groups = []
    for pid, p in advisories.items():
        items = [i for i in p["items"] if i["url"] in picks] if picks is not None else p["items"][:UNCURATED_PER_PUBLISHER]
        if items:
            adv_groups.append({"name": p["name"], "kind": p["kind"], "items": items})

    si, xe, dv = rel.get("sea_intelligence"), rel.get("xeneta"), rel.get("divergence")
    issue = date.fromisoformat(editorial["issue_date"])
    key = worldmap.key_items(j.get("storm_areas", []), j.get("inbound", []), j["storms"])
    field = ((snap["sources"].get("storm_field") or {}).get("data") or {}).get("points") or []
    # Shade only cells that belong to an area in the key, so every splodge on the map has a number.
    keyed = {tuple(m) for a in j.get("storm_areas", []) for m in a.get("members", [])}
    below_rough = pb.SEVERITY_SEA_M["watch"] - 0.1
    field = [p if (p[0], p[1]) in keyed else [p[0], p[1], min(p[2], below_rough), p[3]] for p in field]
    return {
        "ed": editorial,
        "meta": meta,
        "issue_long": f"{issue.strftime('%A')} {issue.day} {issue.strftime('%B %Y')}",
        "generated_at": snap["generated_at"],
        "watchlist": j["watchlist"],
        "port_board": j.get("ports_status", []),
        "ports_flagged": [p for p in j.get("ports_status", []) if p["status"] != "normal"],
        "inbound": j.get("inbound", []),
        "status_labels": pb.STATUS_LABEL,
        "status_colours": pb.STATUS_COLOUR,
        "issue_number": meta.get("issue_number"),
        "world_map_svg": worldmap.world_map(key, field),
        "europe_map_svg": worldmap.north_europe_map(j.get("ports_status", []), key, field),
        "key_items": key,
        "field_ok": bool(field),
        "severity_labels": pb.SEVERITY_LABEL,
        "severity_colours": pb.SEVERITY_COLOUR,
        "severity_sea": pb.SEVERITY_SEA_M,
        "health_names": HEALTH_NAMES,
        "health_words": HEALTH_WORDS,
        "congestion_missing": any(p["data_gaps"] for p in j.get("ports_status", [])),
        "ports": ports,
        "lanes": lanes,
        "day_keys": day_keys,
        "congestion": j.get("congestion") or {},
        "drift": [d for d in j["forecast_drift"] if d["id"] in PORT_IDS or _crosses_limit(d)][:5],
        "storms": sorted(j["storms"], key=lambda s: (not s.get("nearby"), s["nearby"][0]["distance_km"] if s.get("nearby") else 0)),
        "storms_near": [s for s in j["storms"] if s.get("nearby")],
        "by_id": BY_ID,
        "si": si,
        "xe": xe,
        "dv": dv,
        "dumbbell_svg": charts.carrier_dumbbell(si, xe),
        "trend_svg": charts.global_trend(si),
        "adv_groups": adv_groups,
        "health": snap["health"],
        "attributions": snap["attributions"],
        "port_t": PORT_THRESHOLDS,
        "lane_t": LANE_THRESHOLDS,
        "deteriorating_count": len(j["deteriorating"]),
    }


def render_issue(d: Path, snap: dict, editorial: dict, meta: dict) -> Path:
    from weasyprint import HTML

    env = _env()
    ctx = context(snap, editorial, meta)
    html = env.get_template("issue.html.j2").render(**ctx)
    (d / "issue.html").write_text(html)
    pdf_path = d / f"port-brief-{editorial['issue_date']}.pdf"
    HTML(string=html, base_url=str(TEMPLATES)).write_pdf(pdf_path)

    (d / "email.html").write_text(env.get_template("email.html.j2").render(**ctx))
    (d / "email.txt").write_text(env.get_template("email.txt.j2").render(**ctx))
    _preview(pdf_path, d / "preview.png")
    return pdf_path


def _preview(pdf_path: Path, out: Path) -> None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    pdf = pdfium.PdfDocument(str(pdf_path))
    pdf[0].render(scale=1.4).to_pil().save(out)
