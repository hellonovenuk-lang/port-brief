"""Route strips: each trade route into the UK as a chain of sea areas with this week's severity."""

from __future__ import annotations

from port_brief.config import playbook as pb
from port_brief.config.routes import ROUTES, SEGMENT_SHORT

RANK = {"none": 0, "watch": 1, "likely": 2, "extreme": 3}


def area_levels(storm_areas: list[dict], inbound: list[dict]) -> dict[str, dict]:
    """Worst severity per sea-area id, from the storm field and the tracked lanes."""
    levels: dict[str, dict] = {}
    for item in list(storm_areas) + list(inbound):
        cur = levels.get(item["id"])
        if cur is None or RANK[item["level"]] > RANK[cur["level"]]:
            levels[item["id"]] = {"level": item["level"], "peak_sea": item.get("peak_sea"),
                                  "from_day": item.get("from_day"), "to_day": item.get("to_day")}
    return levels


def route_strips(storm_areas: list[dict], inbound: list[dict]) -> list[dict]:
    levels = area_levels(storm_areas, inbound)
    out = []
    for r in ROUTES:
        segments = []
        for sid in r["segments"]:
            hit = levels.get(sid, {})
            segments.append({"id": sid, "short": SEGMENT_SHORT.get(sid, sid), "level": hit.get("level", "none")})
        worst = max((s["level"] for s in segments), key=RANK.get, default="none")
        out.append({
            "id": r["id"], "name": r["name"], "segments": segments, "level": worst,
            "severity": pb.SEVERITY_LABEL.get(worst, "Calm"),
            "delay": pb.INBOUND_DELAY.get(worst, pb.NO_ROUTE_DELAY),
        })
    return out
