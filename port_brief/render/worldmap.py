"""Two static maps for the weather section.

World map: the storm field (six-day peak seas, shaded only where Rough or worse) with a small
number on each flagged sea area or nearby tropical storm. No other words go on the map; the
numbers key into the table printed beneath it.
North Europe map: the eight ports coloured by this week's status, plus the same field and numbers.

Land is Natural Earth (public domain) via world-atlas TopoJSON, decoded here so no GIS
libraries are needed.
"""

from __future__ import annotations

import io
import json
import math
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402

from port_brief.config import playbook as pb  # noqa: E402
from port_brief.config.locations import BY_ID  # noqa: E402
from port_brief.render import charts  # noqa: E402  (registers fonts and the light theme)

GEO = Path(__file__).parent / "geo"
LAND = "#e4e3dc"
COAST = "#b9b8ae"
INK = charts.INK
MUTED = charts.MUTED

WORLD_EXTENT = (-100, 150, -46, 68)  # every route into Europe; the empty Pacific is left out
NORTH_EUROPE_EXTENT = (-8.5, 11, 48.6, 56.3)


@lru_cache(maxsize=2)
def land_rings(resolution: str = "110m") -> list[list[tuple[float, float]]]:
    """Decode a world-atlas TopoJSON 'land' object into lon/lat rings."""
    topo = json.loads((GEO / f"land-{resolution}.json").read_text())
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(indices):
        out = []
        for i in indices:
            pts = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
            out.extend(pts if not out else pts[1:])
        return out

    rings = []
    for geom in topo["objects"]["land"]["geometries"]:
        polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        for poly in polys:
            r = _unwrap(ring(poly[0]))  # outer ring; holes (inland lakes) are omitted at this scale
            if min(p[1] for p in r) < -80:
                continue  # Antarctica: outside both maps, and its ring wraps the pole
            rings.append(r)
            # Rings that cross the date line (Russia, Fiji) are drawn again shifted by 360 degrees.
            if max(p[0] for p in r) > 180:
                rings.append([(x - 360, y) for x, y in r])
            if min(p[0] for p in r) < -180:
                rings.append([(x + 360, y) for x, y in r])
    return rings


def _unwrap(r):
    """Make longitudes continuous so a ring crossing the date line is not drawn across the map."""
    out = [r[0]]
    for x, y in r[1:]:
        px = out[-1][0]
        while x - px > 180:
            x -= 360
        while x - px < -180:
            x += 360
        out.append((x, y))
    return out


def _base(ax, extent, resolution):
    x0, x1, y0, y1 = extent
    for r in land_rings(resolution):
        xs = [p[0] for p in r]
        if max(xs) < x0 - 5 or min(xs) > x1 + 5:
            continue
        ax.add_patch(Polygon(r, closed=True, facecolor=LAND, edgecolor=COAST, linewidth=0.3, zorder=1))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect(1 / math.cos(math.radians((y0 + y1) / 2)))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(COAST)
        s.set_linewidth(0.5)


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.02, facecolor="white")
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index("<svg"):]


# GDACS storm wording to our three-step severity.
STORM_LEVEL = [("hurricane", "extreme"), ("typhoon", "extreme"), ("cyclone", "extreme"),
               ("storm", "likely"), ("depression", "watch")]


def key_items(areas: list[dict], inbound: list[dict], storms: list[dict]) -> list[dict]:
    """One numbered list shared by both maps and the key table, most severe first.

    Every rough area in the storm field gets a row; tracked lanes flagged for wind alone, and
    tropical storms near a route, are added when no area already covers them."""
    rank = {"watch": 1, "likely": 2, "extreme": 3}
    items = [{**a, "kind": "sea"} for a in areas]
    by_id = {i["id"]: i for i in items}
    for lane in inbound:
        if lane["id"] in by_id:
            area = by_id[lane["id"]]
            if rank[lane["level"]] > rank[area["level"]]:
                area.update(level=lane["level"], severity=lane["severity"], delay=lane["delay"])
            continue
        loc = BY_ID[lane["id"]]
        items.append({**lane, "lon": loc["lon"], "lat": loc["lat"], "kind": "sea"})
    for s in storms:
        if not s.get("nearby"):
            continue
        sev = (s.get("severity") or "").lower()
        level = next((lvl for word, lvl in STORM_LEVEL if word in sev), "watch")
        near = BY_ID[s["nearby"][0]["id"]]
        items.append({"id": f"storm-{s.get('event_id')}", "name": f"Tropical storm {s['name']}", "kind": "storm",
                      "lon": s["lon"], "lat": s["lat"], "level": level, "severity": pb.SEVERITY_LABEL[level],
                      "from_day": None, "to_day": None, "peak_sea": None, "delay": pb.INBOUND_DELAY[level],
                      "trades": f"{s.get('severity') or 'Tropical storm'}, {s['nearby'][0]['distance_km']} km from {near['name']}"})
    order = {"extreme": 0, "likely": 1, "watch": 2}
    items.sort(key=lambda x: order[x["level"]])
    for n, item in enumerate(items, start=1):
        item["n"] = n
    return items


def _storm_field(ax, field: list[list], extent):
    """Shade the six-day peak sea height where it reaches the Rough threshold or more."""
    if not field or len(field) < 10:
        return
    import numpy as np
    from matplotlib.tri import Triangulation

    xs = np.array([p[0] for p in field], dtype=float)
    ys = np.array([p[1] for p in field], dtype=float)
    zs = np.array([p[2] for p in field], dtype=float)
    tri = Triangulation(xs, ys)
    # Don't bridge gaps between corridors or across continents.
    t = tri.triangles
    edge = np.maximum.reduce([np.hypot(xs[t[:, a]] - xs[t[:, b]], ys[t[:, a]] - ys[t[:, b]]) for a, b in ((0, 1), (1, 2), (2, 0))])
    tri.set_mask(edge > 6.5)
    levels = [pb.SEVERITY_SEA_M["watch"], pb.SEVERITY_SEA_M["likely"], pb.SEVERITY_SEA_M["extreme"], 40]
    steps = ["watch", "likely", "extreme"]
    plt.rcParams["hatch.color"] = "#4a2e0c"
    plt.rcParams["hatch.linewidth"] = 0.35
    ax.tricontourf(tri, zs, levels=levels, colors=[pb.SEVERITY_COLOUR[k] for k in steps],
                   hatches=[pb.SEVERITY_HATCH[k] for k in steps], alpha=0.8, zorder=0.5, antialiased=True)


def _marker(ax, x, y, n):
    ax.scatter([x], [y], s=52, color="white", edgecolor=INK, linewidth=0.7, zorder=7)
    ax.text(x, y, str(n), ha="center", va="center_baseline", fontsize=5.6, fontweight="bold", color=INK, zorder=8)


def world_map(items: list[dict], field: list[list]) -> str:
    fig, ax = plt.subplots(figsize=(6.9, 3.4))
    _base(ax, WORLD_EXTENT, "110m")
    _storm_field(ax, field, WORLD_EXTENT)
    x0, x1, y0, y1 = NORTH_EUROPE_EXTENT
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=INK, linewidth=0.7, zorder=4))
    placed: list[tuple[float, float]] = []
    for item in items:
        if item["lon"] is None:
            continue  # the "other rough areas" row has no single position
        if x0 <= item["lon"] <= x1 and y0 <= item["lat"] <= y1:
            continue  # numbered on the North Europe map
        x, y = item["lon"], item["lat"]
        # Nudge a marker that would sit on top of one already placed.
        for _ in range(6):
            if all(abs(x - px) > 4.5 or abs(y - py) > 3.5 for px, py in placed):
                break
            y -= 4
        placed.append((x, y))
        _marker(ax, x, y, item["n"])
    return _svg(fig)


def north_europe_map(ports_status: list[dict], items: list[dict], field: list[list]) -> str:
    fig, ax = plt.subplots(figsize=(3.4, 2.9))
    _base(ax, NORTH_EUROPE_EXTENT, "50m")
    _storm_field(ax, field, NORTH_EUROPE_EXTENT)
    x0, x1, y0, y1 = NORTH_EUROPE_EXTENT
    for item in items:
        if item["lon"] is not None and x0 <= item["lon"] <= x1 and y0 <= item["lat"] <= y1:
            _marker(ax, item["lon"], item["lat"], item["n"])
    for p in ports_status:
        lon, lat = PORT_MAP_COORDS[p["id"]]
        off = PORT_LABEL_OFFSET.get(p["id"], (5, 2))
        ax.scatter([lon], [lat], s=22, color=pb.STATUS_COLOUR[p["status"]], edgecolor="white", linewidth=0.8, zorder=5)
        ax.annotate(p["name"], (lon, lat), textcoords="offset points", xytext=off,
                    fontsize=6.8, color=INK, zorder=6, ha="right" if off[0] < 0 else "left")
    return _svg(fig)


# Lanes inside the North Europe map frame, drawn there rather than on the world map.
EUROPE_MAP_LANES = {"dover_strait", "german_bight", "western_approaches"}

# Ports are drawn at the terminals, not at the offshore points used for the sea forecast.
PORT_MAP_COORDS = {
    "felixstowe": (1.32, 51.95), "london_gateway": (0.48, 51.50), "southampton": (-1.40, 50.90),
    "liverpool": (-3.02, 53.45), "rotterdam": (4.05, 51.95), "antwerp": (4.35, 51.27),
    "bremerhaven": (8.58, 53.55), "hamburg": (9.97, 53.54),
}

# Hand-placed label offsets (points) so neighbouring ports don't collide.
PORT_LABEL_OFFSET = {
    "felixstowe": (-4, 5), "london_gateway": (-5, -2), "southampton": (-4, -9), "liverpool": (-4, 2),
    "rotterdam": (4, 3), "antwerp": (4, -8), "bremerhaven": (-4, 4), "hamburg": (4, -8),
}
