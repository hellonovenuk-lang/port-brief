"""GDACS active tropical cyclones. Fills the gap left by Open-Meteo, which has no storm tracks."""

from __future__ import annotations

import math
from datetime import timedelta

from port_brief.config.locations import LOCATIONS
from port_brief.sources.base import Context, SourceResult, http_get

EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
ATTRIBUTION = "Tropical cyclone data: GDACS (Global Disaster Alert and Coordination System), European Commission JRC / UN OCHA"

LIKELY_KM = 500
WATCH_KM = 1200


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(source="cyclones", attribution=ATTRIBUTION)
    params = {
        "eventlist": "TC",
        "alertlevel": "Green;Orange;Red",
        "fromDate": (ctx.now - timedelta(days=7)).strftime("%Y-%m-%d"),
        "toDate": ctx.now.strftime("%Y-%m-%d"),
    }
    resp = http_get(ctx, "cyclones", EVENTS_URL, params=params)
    features = resp.json().get("features", [])

    storms = []
    for feat in features:
        props = feat.get("properties", {})
        if str(props.get("iscurrent", "")).lower() != "true":
            continue
        lon, lat = feat["geometry"]["coordinates"][:2]
        nearby = []
        for loc in LOCATIONS:
            dist = haversine_km(lat, lon, loc["lat"], loc["lon"])
            if dist <= WATCH_KM:
                nearby.append({"id": loc["id"], "distance_km": round(dist), "level": "likely" if dist <= LIKELY_KM else "watch"})
        storms.append({
            "event_id": props.get("eventid"),
            "name": (props.get("name") or props.get("eventname") or "").replace("Tropical Cyclone ", ""),
            "alert_level": props.get("alertlevel"),
            "severity": ((props.get("severitydata") or {}).get("severitytext") or "").split(" (")[0] or None,
            "lat": lat,
            "lon": lon,
            "updated": props.get("todate"),
            "url": (props.get("url") or {}).get("report"),
            "nearby": sorted(nearby, key=lambda n: n["distance_km"]),
        })
    result.data = {"storms": storms, "thresholds_km": {"likely": LIKELY_KM, "watch": WATCH_KM}}
    return result
