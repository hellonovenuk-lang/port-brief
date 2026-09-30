"""Open-Meteo Marine + Forecast APIs: hourly sea state and wind for every port and lane.

Free tier is non-commercial only (see README licence section). Data is CC BY 4.0.
"""

from __future__ import annotations

from port_brief.config.locations import LOCATIONS
from port_brief.sources.base import Context, SourceResult, http_get

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7

MARINE_VARS = [
    "wave_height", "wave_direction", "swell_wave_height", "swell_wave_period",
    "swell_wave_direction", "wind_wave_height", "ocean_current_velocity", "ocean_current_direction",
]
WIND_VARS = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


def _batch_params(variables: list[str]) -> dict:
    return {
        "latitude": ",".join(str(loc["lat"]) for loc in LOCATIONS),
        "longitude": ",".join(str(loc["lon"]) for loc in LOCATIONS),
        "hourly": ",".join(variables),
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }


def _as_list(payload) -> list:
    return payload if isinstance(payload, list) else [payload]


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(
        source="marine_weather",
        attribution=ATTRIBUTION,
        licence_note="Open-Meteo free API is non-commercial only; a commercial plan is required once subscribers pay.",
    )
    series: dict[str, dict] = {loc["id"]: {"time": None} for loc in LOCATIONS}

    for label, url, variables, extra in (
        ("marine", MARINE_URL, MARINE_VARS, {}),
        ("wind", FORECAST_URL, WIND_VARS, {"wind_speed_unit": "ms"}),
    ):
        try:
            resp = http_get(ctx, "marine_weather", url, params={**_batch_params(variables), **extra})
            payload = _as_list(resp.json())
        except Exception as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        if len(payload) != len(LOCATIONS):
            result.errors.append(f"{label}: expected {len(LOCATIONS)} locations, got {len(payload)}")
            continue
        for loc, block in zip(LOCATIONS, payload):
            hourly = block.get("hourly", {})
            if series[loc["id"]]["time"] is None:
                series[loc["id"]]["time"] = hourly.get("time")
            for var in variables:
                series[loc["id"]][var] = hourly.get(var)

    missing = [loc_id for loc_id, s in series.items() if not s.get("wave_height") or all(v is None for v in s["wave_height"])]
    if missing:
        result.errors.append(f"no marine data (grid over land?) for: {', '.join(missing)}")

    if len(result.errors) >= 2 and not any(s.get("wind_speed_10m") for s in series.values()):
        result.status = "failed"
    elif result.errors:
        result.status = "partial"

    result.data = {
        "units": {"wind": "m/s", "gust": "m/s", "wave": "m", "period": "s", "current": "km/h", "direction": "deg (from; current: towards)"},
        "forecast_days": FORECAST_DAYS,
        "hourly": series,
    }
    return result
