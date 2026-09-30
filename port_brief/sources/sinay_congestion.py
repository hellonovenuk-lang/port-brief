"""Sinay Congestion API v1: live occupancy, time-in-port and vessel counts for our ports.

Needs SINAY_API_KEY in the environment. Missing key -> skipped; any error -> failed.
Either way the rest of the run continues, so this feed can be dropped at any time.
"""

from __future__ import annotations

import os

from port_brief.config.locations import PORTS
from port_brief.sources.base import Context, SourceResult, http_get

BASE_URL = "https://api.sinay.ai/congestion/api/v1"
ATTRIBUTION = "Port congestion data: Sinay (sinay.ai)"


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(source="sinay_congestion", attribution=ATTRIBUTION,
                          licence_note="Check Sinay plan terms allow republishing figures in a paid newsletter.")
    key = os.environ.get("SINAY_API_KEY", "").strip()
    if not key:
        result.status = "skipped"
        result.errors.append("SINAY_API_KEY not set")
        return result

    codes = [p["unlocode"] for p in PORTS][:10]  # API max is 10 ports per batch
    resp = http_get(
        ctx, "sinay_congestion", f"{BASE_URL}/congestion/batch",
        method="POST", json_body={"portCodes": codes}, headers={"API_KEY": key, "Accept": "application/json"},
    )
    payload = resp.json()
    rows = payload.get("results", payload if isinstance(payload, list) else [])

    by_code = {}
    for row in rows:
        code = row.get("portCode")
        if not code:
            continue
        occ = row.get("rateOccupation") or {}
        commercial = occ.get("commercialVessels") or {}
        cargo = occ.get("cargo") or {}
        tip = (row.get("time") or {}).get("timeInPortStatistics") or {}
        counts = row.get("vesselsInPortCount") or {}
        by_code[code] = {
            "occupancy_pct": commercial.get("rateOccupationPercentage"),
            "occupancy_gap_vs_mean_pct": commercial.get("rateOccupationGapWithMean"),
            "cargo_occupancy_pct": cargo.get("rateOccupationPercentage"),
            "cargo_gap_vs_mean_pct": cargo.get("rateOccupationGapWithMean"),
            "time_in_port_median_h": tip.get("median"),
            "time_in_port_max_h": tip.get("max"),
            "vessels_in_port": counts.get("commercialVessels"),
            "cargo_vessels_in_port": counts.get("cargo"),
        }

    ports = {}
    for p in PORTS:
        if p["unlocode"] in by_code:
            ports[p["id"]] = {"unlocode": p["unlocode"], **by_code[p["unlocode"]]}
    missing = [p["id"] for p in PORTS if p["id"] not in ports]
    if missing:
        result.errors.append(f"no congestion data for: {', '.join(missing)}")
        result.status = "partial" if ports else "failed"
    result.data = {"ports": ports, "raw_count": len(rows)}
    return result
