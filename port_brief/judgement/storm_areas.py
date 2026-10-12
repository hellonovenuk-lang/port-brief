"""Turn the storm field into named sea areas with a severity and timing.

Each rough grid cell is assigned to its nearest named sea area (like shipping-forecast zones):
the tracked lanes plus a small gazetteer of other areas on the routes into Europe. Every area
with rough cells becomes one numbered row in the map key, so nothing shaded goes unexplained,
and a large storm spanning several areas is described where each part of it actually is.
"""

from __future__ import annotations

import math

from port_brief.config import playbook as pb
from port_brief.config.locations import LOCATIONS


# Further named sea areas (beyond the tracked lanes): name, lon, lat, routes affected, and
# whether a main route into Europe crosses it (if not, delays apply only to ships routed there).
GAZETTEER = [
    ("North Sea", 3, 56, "North Sea feeders and calls at the UK east coast and continental hubs", True),
    ("North of Scotland", -8, 59, "northabout routings and Scandinavian services", False),
    ("Off Portugal", -13, 40, "Asia, Mediterranean and West Africa services into the UK", True),
    ("North-west Atlantic", -55, 42, "transatlantic services from the US East Coast and Canada", True),
    ("Azores", -28, 37, "transatlantic and Caribbean services", True),
    ("Caribbean", -72, 15, "Caribbean, Gulf and Panama services to Europe", True),
    ("Off West Africa", -22, 15, "West Africa and Cape-routed services", True),
    ("Gulf of Guinea", 2, 0, "West Africa services", True),
    ("Off Namibia", 8, -24, "Asia–North Europe services routed via the Cape", True),
    ("South Atlantic", -18, -28, "South America East Coast and Cape-routed services", False),
    ("Mozambique Channel", 41, -18, "East Africa and Cape-routed services", False),
    ("Southern Indian Ocean", 70, -35, "Australia and Cape-routed services", False),
    ("Western Indian Ocean", 60, -10, "Asia–Europe services via the Cape", True),
    ("Red Sea", 38, 20, "Asia–Europe services via Suez", True),
    ("Mediterranean", 18, 35, "Mediterranean and Asia–Europe services via Suez", True),
    ("Bay of Bengal", 88, 14, "Bangladesh and east India services", False),
    ("South China Sea", 114, 14, "sailings from China, Vietnam and Singapore", True),
    ("East China Sea", 124, 29, "sailings from Shanghai, Ningbo and Korea", True),
]


def _dist(a, b) -> float:
    dx = (a[0] - b[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot(dx, a[1] - b[1])


def level_for(hs: float) -> str | None:
    for level in ("extreme", "likely", "watch"):
        if hs >= pb.SEVERITY_SEA_M[level]:
            return level
    return None


def zones() -> list[dict]:
    lane_zones = [{"id": loc["id"], "name": loc["name"], "lon": loc["lon"], "lat": loc["lat"],
                   "trades": loc.get("inbound_trades", ""), "on_lane": True}
                  for loc in LOCATIONS if loc["kind"] == "lane"]
    extra = [{"id": "area-" + n.lower().replace(" ", "-"), "name": n, "lon": x, "lat": y, "trades": t, "on_lane": route}
             for n, x, y, t, route in GAZETTEER]
    return lane_zones + extra


MAX_AREAS = 10


def storm_areas(points: list[list]) -> list[dict]:
    zs = zones()
    grouped: dict[str, list] = {}
    for p in points:
        if not level_for(p[2]):
            continue
        z = min(zs, key=lambda z: _dist((z["lon"], z["lat"]), p))
        grouped.setdefault(z["id"], []).append(p)
    by_id = {z["id"]: z for z in zs}
    areas = []
    for zid, group in grouped.items():
        peak = max(group, key=lambda p: p[2])
        level = level_for(peak[2])
        if len(group) < 2 and level == "watch":
            continue  # a single rough cell is noise at this resolution
        z = by_id[zid]
        days = sorted(p[3] for p in group)
        areas.append({
            "id": zid, "name": z["name"], "trades": z["trades"], "on_lane": z["on_lane"],
            "lon": peak[0], "lat": peak[1], "level": level, "severity": pb.SEVERITY_LABEL[level],
            "peak_sea": peak[2], "peak_day": peak[3], "from_day": days[0], "to_day": days[-1],
            "delay": pb.INBOUND_DELAY[level] if z["on_lane"] else pb.OFF_ROUTE_DELAY, "cells": len(group),
            "members": [[p[0], p[1]] for p in group],
        })
    order = {"extreme": 0, "likely": 1, "watch": 2}
    areas.sort(key=lambda a: (order[a["level"]], not a["on_lane"], -a["peak_sea"]))
    if len(areas) > MAX_AREAS:
        # Keep the key short: the least severe extra areas share one unnumbered note.
        extra = areas[MAX_AREAS - 1:]
        areas = areas[:MAX_AREAS - 1]
        areas.append({**extra[0], "id": "area-other", "name": "Other rough areas",
                      "members": [m for a in extra for m in a["members"]],
                      "trades": ", ".join(a["name"] for a in extra), "lon": None, "lat": None})
    return areas
