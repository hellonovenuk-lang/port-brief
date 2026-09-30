"""Port Brief command line.

    python -m port_brief collect [--dry-run] [--only SOURCE ...]
    python -m port_brief judge [--dry-run]
    python -m port_brief draft [--dry-run] [--date YYYY-MM-DD]     # fallback editorial + validate + render
    python -m port_brief validate --date YYYY-MM-DD
    python -m port_brief render --date YYYY-MM-DD
    python -m port_brief all [--dry-run]                             # collect + judge + draft
"""

from __future__ import annotations

import argparse
import json
import sys

from port_brief.collect import SOURCES, collect, load_snapshot, save_snapshot
from port_brief.sources.base import Context


def cmd_collect(args) -> dict:
    snap = collect(Context(dry_run=args.dry_run), only=args.only)
    print(f"snapshot {snap['run_id']} ({snap['mode']})")
    for name, h in snap["health"].items():
        print(f"  {name:22} {h['status']:8} {'; '.join(h['errors'])[:160]}")
    return snap


def cmd_judge(args) -> dict:
    from port_brief.judgement.weather_risk import judge

    snap = load_snapshot(dry_run=args.dry_run)
    j = judge(snap)
    save_snapshot(snap)
    print(f"judged {len(j['locations'])} locations; watchlist:")
    for w in j["watchlist"]:
        print(f"  {w['level']:6} {w['trend']:13} {w['name']:32} peak {w['peak_day']} {', '.join(w['causes'])}")
    if j["forecast_drift"]:
        print(f"forecast drift items: {len(j['forecast_drift'])}")
    return j


def cmd_draft(args) -> int:
    from port_brief.editorial.build import build_draft

    ok = build_draft(dry_run=args.dry_run, issue_date=args.date)
    return 0 if ok else 1


def cmd_validate(args) -> int:
    from port_brief.editorial.build import validate_draft

    errors = validate_draft(args.date, dry_run=args.dry_run)
    print(json.dumps(errors, indent=2) if errors else "editorial valid")
    return 1 if errors else 0


def cmd_render(args) -> int:
    from port_brief.editorial.build import render_draft

    out = render_draft(args.date, dry_run=args.dry_run)
    print(f"rendered {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="port_brief")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "judge", "draft", "validate", "render", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--dry-run", action="store_true", help="serve all HTTP from data/cache; no network")
        sp.add_argument("--date", help="issue date YYYY-MM-DD (default: today UTC)")
        if name == "collect":
            sp.add_argument("--only", nargs="+", choices=list(SOURCES), help="re-run these sources into the latest snapshot")
    args = p.parse_args(argv)

    if args.cmd == "collect":
        cmd_collect(args)
    elif args.cmd == "judge":
        cmd_judge(args)
    elif args.cmd == "draft":
        return cmd_draft(args)
    elif args.cmd == "validate":
        return cmd_validate(args)
    elif args.cmd == "render":
        return cmd_render(args)
    elif args.cmd == "all":
        args.only = None
        cmd_collect(args)
        cmd_judge(args)
        return cmd_draft(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
