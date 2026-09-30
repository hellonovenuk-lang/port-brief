"""Assemble an issue: freeze the snapshot into drafts/<date>/, write a facts sheet for the
editor (Claude), make sure a valid editorial.json exists, and render the PDF + email."""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from port_brief import paths
from port_brief.collect import load_snapshot
from port_brief.editorial import schema


def issue_date_or_today(issue_date: str | None) -> str:
    return issue_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def draft_dir(issue_date: str, dry_run: bool = False) -> Path:
    return (paths.DRAFTS / "dry-run" / issue_date) if dry_run else (paths.DRAFTS / issue_date)


def _read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def facts_markdown(snap: dict, issue_date: str) -> str:
    """A compact brief of every figure the writer may use. The validator enforces it."""
    j = snap["judgement"]
    rel = snap["sources"]["schedule_reliability"]["data"]
    lines = [f"# Facts for Port Brief {issue_date}", "",
             f"Forecast issued {snap['generated_at']}. Levels: none < watch < likely.", "",
             "## Watchlist (ranked)", ""]
    for w in j["watchlist"]:
        lines.append(f"- `{w['id']}` {w['name']} [{w['kind']}, {w['region']}]: {w['level']}, trend {w['trend']}, "
                     f"peak {schema.day_label(w['peak_day'])}; causes {', '.join(w['causes']) or '-'}; {' | '.join(w['reasons'])}")
    lines += ["", "## All locations: daily peaks (gust m/s / sea m / level)", ""]
    for a in j["locations"].values():
        cells = [f"{schema.day_label(d['date'])}: {d['gust_max']}/{d['hs_max']}/{d['level']}" for d in a["days"]]
        lines.append(f"- {a['name']} ({a['kind']}, outlook {a['outlook_3_5d']}, trend {a['trend']}): " + "; ".join(cells))
    if j["forecast_drift"]:
        lines += ["", "## Forecast drift since previous run", ""]
        for d in j["forecast_drift"]:
            lines.append(f"- {d['name']} {schema.day_label(d['date'])}: gust {d['gust_prev']} -> {d['gust_now']} ({d['gust_delta']:+}); "
                         f"sea {d['hs_prev']} -> {d['hs_now']} ({d['hs_delta']:+})" if d['gust_delta'] is not None and d['hs_delta'] is not None
                         else f"- {d['name']} {d['date']}: {d}")
    if j["storms"]:
        lines += ["", "## Tropical cyclones (GDACS, current)", ""]
        for s in j["storms"]:
            near = ", ".join(f"{n['id']} {n['distance_km']} km ({n['level']})" for n in s["nearby"]) or "no tracked location within 1200 km"
            lines.append(f"- {s['name']}: {s['severity']}; {near}")
    if j["congestion"]:
        lines += ["", "## Congestion (Sinay)", ""]
        for pid, c in j["congestion"].items():
            lines.append(f"- {c['name']}: occupancy {c['occupancy_pct']}% (gap vs Sinay mean {c['occupancy_gap_vs_mean_pct']} pp; "
                         f"vs our trailing avg {c['vs_trailing_pp']} pp), median time in port {c['time_in_port_median_h']} h, vessels {c['vessels_in_port']}")
    else:
        lines += ["", "## Congestion (Sinay)", "", f"- unavailable: {snap['health']['sinay_congestion']['errors']}"]
    lines += ["", "## Schedule reliability", ""]
    for key in ("sea_intelligence", "xeneta"):
        r = rel.get(key)
        if not r:
            lines.append(f"- {key}: unavailable")
            continue
        stale = f" (STALE since {r['stale_since']})" if r.get("stale_since") else ""
        lines.append(f"- {r['source']} {r['period']}{stale}: global {r['global_pct']}%; MoM {r.get('mom_pp', r.get('global_mom_pp'))} pp; "
                     f"YoY {r.get('yoy_pp')} pp; avg delay late {r.get('avg_delay_late_days')} d. Method: {r['methodology']}")
        lines.append("  - carriers: " + ", ".join(f"{c['rank']}. {c['carrier']} {c['pct']}%" for c in r["carriers"]))
    dv = rel.get("divergence")
    if dv and dv.get("comparable"):
        lines.append(f"- Divergence {dv['period']}: global gap {dv['global_gap_pp']} pp (SI minus Xeneta). Largest carrier gap: "
                     f"{dv['largest_gap']['carrier']} {dv['largest_gap']['gap_pp']} pp. Per carrier: "
                     + ", ".join(f"{c['carrier']} {c['gap_pp']:+}" for c in dv["carriers"]))
    elif dv:
        lines.append(f"- Divergence: {dv['note']}")
    lines += ["", "## Advisories (past week; `new` = not in a previous issue)", ""]
    for p in snap["sources"]["advisories"]["data"]["publishers"].values():
        for i in p["items"]:
            lines.append(f"- [{p['name']}] {i['published']} {'NEW ' if i['is_new'] else ''}{i['title']} <{i['url']}> ({i['via']})")
    lines += ["", "## Source health", ""]
    for name, h in snap["health"].items():
        lines.append(f"- {name}: {h['status']} {'; '.join(h['errors'])[:200]}")
    return "\n".join(lines) + "\n"


def prepare(issue_date: str | None = None, dry_run: bool = False) -> tuple[str, Path, dict]:
    issue_date = issue_date_or_today(issue_date)
    d = draft_dir(issue_date, dry_run)
    snap = load_snapshot(dry_run=dry_run)
    if "judgement" not in snap:
        raise SystemExit("snapshot has no judgement: run `python -m port_brief judge` first")
    _write(d / "snapshot.json", snap)
    (d / "facts.md").write_text(facts_markdown(snap, issue_date))
    meta = _read(d / "meta.json") or {"issue_date": issue_date, "pdf_token": secrets.token_urlsafe(9)}
    meta.update(run_id=snap["run_id"], mode=snap["mode"])
    _write(d / "meta.json", meta)
    return issue_date, d, snap


def validate_draft(issue_date: str | None, dry_run: bool = False) -> list[str]:
    issue_date = issue_date_or_today(issue_date)
    d = draft_dir(issue_date, dry_run)
    editorial, snap = _read(d / "editorial.json"), _read(d / "snapshot.json")
    if editorial is None or snap is None:
        return ["draft not prepared: run `python -m port_brief draft` first"]
    return schema.validate(editorial, snap, issue_date)


def ensure_editorial(d: Path, snap: dict, issue_date: str) -> dict:
    """Keep a valid human/Claude editorial; otherwise fall back to the template."""
    current = _read(d / "editorial.json")
    if current:
        errors = schema.validate(current, snap, issue_date)
        if not errors:
            return current
        _write(d / "editorial.rejected.json", {"errors": errors, "editorial": current})
        print("editorial.json failed validation; using templated fallback:\n  " + "\n  ".join(errors))
    fb = schema.fallback(snap, issue_date)
    errors = schema.validate(fb, snap, issue_date)
    if errors:
        raise RuntimeError(f"templated fallback failed validation (bug): {errors}")
    _write(d / "editorial.json", fb)
    return fb


def render_draft(issue_date: str | None, dry_run: bool = False) -> Path:
    from port_brief.render.issue import render_issue

    issue_date = issue_date_or_today(issue_date)
    d = draft_dir(issue_date, dry_run)
    snap = _read(d / "snapshot.json")
    editorial = ensure_editorial(d, snap, issue_date)
    return render_issue(d, snap, editorial, _read(d / "meta.json"))


def build_draft(dry_run: bool = False, issue_date: str | None = None) -> bool:
    issue_date, d, snap = prepare(issue_date, dry_run)
    ensure_editorial(d, snap, issue_date)
    out = render_draft(issue_date, dry_run)
    print(f"draft ready: {out}")
    return True
