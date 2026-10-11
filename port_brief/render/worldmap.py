"""Two static maps for the weather section.

World map: only lanes forecast to slow ships, plus storms near tracked locations, are marked.
North Europe map: the eight ports coloured by this week's status, plus any flagged nearby lane.
Calm places are deliberately left off; an empty map is the message on a quiet week.

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
from port_brief.editorial.schema import day_label  # noqa: E402
from port_brief.render import charts  # noqa: E402  (registers fonts and the light theme)

GEO = Path(__file__).parent / "geo"
LAND = "#e4e3dc"
COAST = "#b9b8ae"
INK = charts.INK
MUTED = charts.MUTED
LEVEL_COLOUR = {"watch": pb.STATUS_COLOUR["watch"], "likely": pb.STATUS_COLOUR["disruption"]}

WORLD_EXTENT = (-180, 180, -50, 72)
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


def _label(ax, x, y, title, sub, extent, colour=INK):
    x0, x1, _, _ = extent
    near_europe = -25 < x < 30 and y > 30  # keep labels off the ports-map box
    right = x < x1 - (x1 - x0) * 0.22 and not near_europe
    ax.annotate(f"{title}\n{sub}" if sub else title, (x, y), textcoords="offset points",
                xytext=(7 if right else -7, 0), ha="left" if right else "right", va="center",
                fontsize=7, color=colour, linespacing=1.15, zorder=6)


def world_map(inbound: list[dict], storms: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(6.9, 2.75))
    _base(ax, WORLD_EXTENT, "110m")
    x0, x1, y0, y1 = NORTH_EUROPE_EXTENT
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=INK, linewidth=0.8, zorder=4))

    for item in inbound:
        loc = BY_ID[item["id"]]
        if x0 <= loc["lon"] <= x1 and y0 <= loc["lat"] <= y1:
            continue  # shown on the North Europe map
        colour = LEVEL_COLOUR[item["level"]]
        ax.scatter([loc["lon"]], [loc["lat"]], s=150 if item["level"] == "likely" else 90, color=colour,
                   alpha=0.35, edgecolor=colour, linewidth=1, zorder=5)
        ax.scatter([loc["lon"]], [loc["lat"]], s=10, color=colour, zorder=6)
        when = day_label(item["from_day"]) if item.get("from_day") else ""
        _label(ax, loc["lon"], loc["lat"], item["name"], f"{when}, {item['delay']} late".strip(", "), WORLD_EXTENT)

    for s in storms:
        if not s.get("nearby"):
            continue
        ax.scatter([s["lon"]], [s["lat"]], s=70, facecolor="none", edgecolor=pb.STATUS_COLOUR["disruption"], linewidth=1.2, zorder=5)
        _label(ax, s["lon"], s["lat"], s["name"], s.get("severity") or "", WORLD_EXTENT)
    return _svg(fig)


def north_europe_map(ports_status: list[dict], inbound: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(3.4, 2.9))
    _base(ax, NORTH_EUROPE_EXTENT, "50m")
    x0, x1, y0, y1 = NORTH_EUROPE_EXTENT
    for item in inbound:
        loc = BY_ID[item["id"]]
        if not (x0 <= loc["lon"] <= x1 and y0 <= loc["lat"] <= y1):
            continue
        colour = LEVEL_COLOUR[item["level"]]
        ax.scatter([loc["lon"]], [loc["lat"]], s=300, color=colour, alpha=0.25, edgecolor=colour, linewidth=1, zorder=3)
        low = loc["lat"] < y0 + 1.5
        ax.annotate(f"{item['name']}, {day_label(item['from_day'])}", (loc["lon"], loc["lat"]), textcoords="offset points",
                    xytext=(4 if low else 0, 11 if low else -13), ha="left" if low else "center", va="bottom" if low else "top",
                    fontsize=6.3, color=INK, style="italic", zorder=6)
    for p in ports_status:
        lon, lat = PORT_MAP_COORDS[p["id"]]
        loc = {"lon": lon, "lat": lat}
        ax.scatter([loc["lon"]], [loc["lat"]], s=22, color=pb.STATUS_COLOUR[p["status"]], edgecolor="white", linewidth=0.8, zorder=5)
        ax.annotate(p["name"], (loc["lon"], loc["lat"]), textcoords="offset points", xytext=PORT_LABEL_OFFSET.get(p["id"], (5, 2)),
                    fontsize=6.8, color=INK, zorder=6, ha="right" if PORT_LABEL_OFFSET.get(p["id"], (5, 2))[0] < 0 else "left")
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
