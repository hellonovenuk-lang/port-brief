"""Orchestrator: run every source in isolation and write one consolidated snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from port_brief import paths
from port_brief.sources import advisories, cyclones, marine_weather, schedule_reliability, sinay_congestion
from port_brief.sources.base import Context, iso, run_source

SOURCES = {
    "marine_weather": marine_weather.fetch,
    "cyclones": cyclones.fetch,
    "sinay_congestion": sinay_congestion.fetch,
    "schedule_reliability": schedule_reliability.fetch,
    "advisories": advisories.fetch,
}


def run_id_for(ctx: Context) -> str:
    return ctx.now.strftime("%Y-%m-%dT%H%MZ")


def snapshot_dir(dry_run: bool) -> Path:
    return paths.DRY_RUN_SNAPSHOTS if dry_run else paths.SNAPSHOTS


def weather_history_path(run_id: str, dry_run: bool) -> Path:
    if dry_run:
        return paths.DRY_RUN_SNAPSHOTS / f"{run_id}.weather.json"
    return paths.WEATHER_HISTORY / f"{run_id}.json"


def write_json(path: Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=2, default=str))


def latest_snapshot_path(dry_run: bool = False) -> Path:
    return snapshot_dir(dry_run) / "latest.json"


def load_snapshot(path: Path | None = None, dry_run: bool = False) -> dict:
    path = path or latest_snapshot_path(dry_run)
    return json.loads(path.read_text())


def save_snapshot(snapshot: dict) -> Path:
    dry = snapshot["mode"] == "dry-run"
    out = snapshot_dir(dry) / f"{snapshot['run_id']}.json"
    write_json(out, snapshot)
    write_json(latest_snapshot_path(dry), snapshot)
    return out


def _externalise_weather(snapshot: dict, dry_run: bool) -> None:
    """Hourly series go to history (for change-over-time), not into the snapshot itself."""
    mw = snapshot["sources"].get("marine_weather", {})
    hourly = mw.get("data", {}).pop("hourly", None)
    if hourly:
        hist = weather_history_path(snapshot["run_id"], dry_run)
        write_json(hist, {"run_id": snapshot["run_id"], "generated_at": snapshot["generated_at"], "hourly": hourly}, compact=True)
        mw["data"]["history_file"] = str(hist.relative_to(paths.ROOT))


def _record_congestion(snapshot: dict, dry_run: bool) -> None:
    sc = snapshot["sources"].get("sinay_congestion", {})
    if dry_run or sc.get("status") not in ("ok", "partial"):
        return
    write_json(paths.CONGESTION_HISTORY / f"{snapshot['run_id']}.json",
               {"run_id": snapshot["run_id"], "ports": sc["data"]["ports"]})


def collect(ctx: Context, only: list[str] | None = None) -> dict:
    if only:
        # Re-run selected sources and patch them into the latest snapshot.
        snapshot = load_snapshot(dry_run=ctx.dry_run)
        for name in only:
            snapshot["sources"][name] = run_source(name, SOURCES[name], ctx).to_dict()
        if "marine_weather" in only:
            _externalise_weather(snapshot, ctx.dry_run)
    else:
        snapshot = {
            "run_id": run_id_for(ctx),
            "generated_at": iso(ctx.now),
            "mode": "dry-run" if ctx.dry_run else "live",
            "sources": {name: run_source(name, fn, ctx).to_dict() for name, fn in SOURCES.items()},
        }
        _externalise_weather(snapshot, ctx.dry_run)
        _record_congestion(snapshot, ctx.dry_run)

    snapshot["health"] = {
        name: {"status": s["status"], "errors": [e for e in s["errors"] if not e.startswith("Traceback")][:3]}
        for name, s in snapshot["sources"].items()
    }
    snapshot["attributions"] = sorted({s["attribution"] for s in snapshot["sources"].values() if s.get("attribution")})
    snapshot["licence_notes"] = sorted({s["licence_note"] for s in snapshot["sources"].values() if s.get("licence_note")})
    save_snapshot(snapshot)
    return snapshot
