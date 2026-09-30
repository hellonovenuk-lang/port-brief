"""Ports and lanes we forecast for, and the thresholds that turn weather into operational risk.

Coordinates for ports sit just offshore of the harbour entrance or pilot station: the
Open-Meteo marine grid returns nulls for points that fall on land.

Thresholds are starting heuristics, not published standards. Tune them per location as
the newsletter builds a track record (see README, "Judgement thresholds").
"""

# Region drives UK relevance in the watchlist ranking.
RELEVANCE = {"uk": 1.5, "north_europe": 1.3, "global": 1.0}

PORT_THRESHOLDS = {
    # Crane operations: STS cranes typically stop around 20 m/s at boom height. 10 m model
    # winds under-read crane height, so gusts are the primary trigger.
    "crane_watch_gust": 15.0,
    "crane_likely_gust": 20.0,
    "crane_watch_wind": 13.0,
    "crane_likely_wind": 17.0,
    # Pilot boarding: suspended in heavy sea or long-period swell.
    "pilot_watch_hs": 2.5,
    "pilot_likely_hs": 3.5,
    "pilot_watch_swell": 1.5,
    "pilot_watch_period": 10.0,
    "pilot_likely_swell": 2.5,
    "pilot_likely_period": 12.0,
}

LANE_THRESHOLDS = {
    "lane_watch_hs": 4.0,
    "lane_likely_hs": 6.0,
    "lane_watch_wind": 17.2,  # Beaufort 8
    "lane_likely_wind": 20.8,  # Beaufort 9
}

# Agulhas: swell from the south-west running against the south-west-flowing current
# steepens waves sharply (abnormal-wave risk).
AGULHAS = {
    "swell_from_min": 200,
    "swell_from_max": 260,
    "min_hs": 4.0,
    "max_opposition_deg": 60,
    "min_current_kmh": 1.5,
}

LOCATIONS = [
    # --- Ports ---
    {"id": "felixstowe", "name": "Felixstowe", "kind": "port", "region": "uk", "lat": 51.92, "lon": 1.45, "unlocode": "GBFXT"},
    {"id": "southampton", "name": "Southampton", "kind": "port", "region": "uk", "lat": 50.67, "lon": -0.95, "unlocode": "GBSOU"},
    {"id": "london_gateway", "name": "London Gateway", "kind": "port", "region": "uk", "lat": 51.52, "lon": 1.10, "unlocode": "GBLGP"},
    {"id": "liverpool", "name": "Liverpool", "kind": "port", "region": "uk", "lat": 53.53, "lon": -3.35, "unlocode": "GBLIV"},
    {"id": "rotterdam", "name": "Rotterdam", "kind": "port", "region": "north_europe", "lat": 51.98, "lon": 3.95, "unlocode": "NLRTM"},
    {"id": "antwerp", "name": "Antwerp", "kind": "port", "region": "north_europe", "lat": 51.42, "lon": 3.10, "unlocode": "BEANR"},
    {"id": "hamburg", "name": "Hamburg", "kind": "port", "region": "north_europe", "lat": 54.00, "lon": 8.10, "unlocode": "DEHAM"},
    {"id": "la_long_beach", "name": "Los Angeles / Long Beach", "kind": "port", "region": "global", "lat": 33.65, "lon": -118.25, "unlocode": "USLAX"},
    {"id": "shanghai", "name": "Shanghai", "kind": "port", "region": "global", "lat": 30.55, "lon": 122.25, "unlocode": "CNSHA"},
    {"id": "singapore", "name": "Singapore", "kind": "port", "region": "global", "lat": 1.20, "lon": 103.85, "unlocode": "SGSIN"},
    # --- Chokepoints and lanes (as briefed) ---
    {"id": "agulhas", "name": "Cape of Good Hope / Agulhas", "kind": "lane", "region": "global", "lat": -35.30, "lon": 22.00, "agulhas": True},
    {"id": "biscay", "name": "Bay of Biscay", "kind": "lane", "region": "uk", "lat": 45.50, "lon": -6.00},
    {"id": "western_approaches", "name": "Western Approaches", "kind": "lane", "region": "uk", "lat": 49.30, "lon": -7.50},
    {"id": "mid_north_atlantic", "name": "Mid-North Atlantic", "kind": "lane", "region": "global", "lat": 47.00, "lon": -30.00},
    {"id": "malacca", "name": "Strait of Malacca", "kind": "lane", "region": "global", "lat": 3.00, "lon": 100.80},
    {"id": "suez", "name": "Suez approaches (Port Said)", "kind": "lane", "region": "global", "lat": 31.55, "lon": 32.40},
    {"id": "panama", "name": "Panama approaches (Colón)", "kind": "lane", "region": "global", "lat": 9.50, "lon": -79.95},
    {"id": "gibraltar", "name": "Strait of Gibraltar", "kind": "lane", "region": "north_europe", "lat": 35.95, "lon": -5.55},
    # --- Added for global lane coverage ---
    {"id": "dover_strait", "name": "Dover Strait", "kind": "lane", "region": "uk", "lat": 51.00, "lon": 1.45},
    {"id": "german_bight", "name": "German Bight", "kind": "lane", "region": "north_europe", "lat": 54.20, "lon": 7.50},
    {"id": "bab_el_mandeb", "name": "Bab-el-Mandeb / Gulf of Aden", "kind": "lane", "region": "global", "lat": 12.40, "lon": 44.00},
    {"id": "arabian_sea", "name": "Arabian Sea", "kind": "lane", "region": "global", "lat": 16.00, "lon": 63.00},
    {"id": "taiwan_strait", "name": "Taiwan Strait", "kind": "lane", "region": "global", "lat": 24.00, "lon": 119.50},
    {"id": "north_pacific", "name": "North Pacific (transpacific)", "kind": "lane", "region": "global", "lat": 45.00, "lon": 170.00},
    {"id": "sri_lanka", "name": "South of Sri Lanka", "kind": "lane", "region": "global", "lat": 5.60, "lon": 80.60},
]

BY_ID = {loc["id"]: loc for loc in LOCATIONS}
PORTS = [loc for loc in LOCATIONS if loc["kind"] == "port"]


def thresholds_for(loc: dict) -> dict:
    base = PORT_THRESHOLDS if loc["kind"] == "port" else LANE_THRESHOLDS
    return {**base, **loc.get("thresholds", {})}
