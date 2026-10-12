"""Storm field: a coarse grid of six-day peak wave heights over the routes into Europe.

Drawn on the weather map as shaded blobs where seas are rough, so readers see where the
weather actually is rather than only at the points we track. Corridors cover the Atlantic,
the Mediterranean and Red Sea, the Indian Ocean and South-East Asia; the Pacific and the far
Southern Ocean are left out because ships bound for Europe don't sail there.
"""

from __future__ import annotations

from functools import lru_cache

from port_brief.sources.base import Context, SourceResult, http_get

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
CHUNK = 150

# (lon_min, lon_max, lat_min, lat_max, step_degrees)
CORRIDORS = [
    (-80, 10, -40, 61, 3),    # Atlantic, Biscay, Western Approaches, North Sea
    (-6, 45, 10, 46, 3),      # Mediterranean, Suez, Red Sea
    (10, 36, -42, 25, 4),     # round the Cape and up East Africa
    (36, 100, -30, 25, 4),    # Indian Ocean, Arabian Sea
    (95, 125, -10, 35, 3),    # Malacca, South China Sea, Taiwan Strait
]


@lru_cache(maxsize=1)
def grid_points() -> list[tuple[float, float]]:
    """Sea points on the corridor grids (land removed with Natural Earth polygons)."""
    from matplotlib.path import Path

    from port_brief.render.worldmap import land_rings

    polys = []
    for ring in land_rings("110m"):
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        polys.append(((min(xs), max(xs), min(ys), max(ys)), Path(ring)))

    def on_land(lon, lat):
        return any(b[0] <= lon <= b[1] and b[2] <= lat <= b[3] and path.contains_point((lon, lat))
                   for b, path in polys)

    points = set()
    for x0, x1, y0, y1, step in CORRIDORS:
        lon = x0
        while lon <= x1:
            lat = y0
            while lat <= y1:
                pacific = lon < -70 and lat < 9  # west of South America: not a route to Europe
                if not pacific and not on_land(lon, lat):
                    points.add((float(lon), float(lat)))
                lat += step
            lon += step
    return sorted(points)


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(source="storm_field", attribution=ATTRIBUTION)
    pts = grid_points()
    out, failed = [], 0
    for i in range(0, len(pts), CHUNK):
        chunk = pts[i:i + CHUNK]
        params = {
            "latitude": ",".join(f"{lat:g}" for _, lat in chunk),
            "longitude": ",".join(f"{lon:g}" for lon, _ in chunk),
            "daily": "wave_height_max",
            "forecast_days": 7,
            "timezone": "UTC",
        }
        try:
            payload = http_get(ctx, "storm_field", MARINE_URL, params=params).json()
        except Exception as exc:
            failed += 1
            result.errors.append(f"chunk {i // CHUNK}: {exc}")
            continue
        payload = payload if isinstance(payload, list) else [payload]
        for (lon, lat), block in zip(chunk, payload):
            daily = block.get("daily") or {}
            vals = daily.get("wave_height_max") or []
            days = daily.get("time") or []
            pairs = [(v, d) for v, d in zip(vals, days) if v is not None]
            if not pairs:
                continue  # coastal cell the marine model treats as land
            peak, day = max(pairs)
            out.append([lon, lat, round(peak, 1), day])

    total = (len(pts) + CHUNK - 1) // CHUNK
    result.status = "failed" if failed == total else ("partial" if failed else "ok")
    result.data = {"points": out, "grid_points": len(pts), "requests": total}
    return result
