import pytest

from port_brief import paths


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Point every data path at a temp directory so tests never touch real history."""
    data = tmp_path / "data"
    mapping = {
        "ROOT": tmp_path,
        "DATA": data,
        "SNAPSHOTS": data / "snapshots",
        "DRY_RUN_SNAPSHOTS": data / "snapshots" / "dry-run",
        "WEATHER_HISTORY": data / "history" / "weather",
        "CONGESTION_HISTORY": data / "history" / "congestion",
        "RELIABILITY": data / "reliability",
        "ADVISORIES": data / "advisories",
        "CACHE": data / "cache",
        "LOGS": data / "logs",
        "FETCH_LOG": data / "logs" / "fetch.jsonl",
        "DRAFTS": tmp_path / "drafts",
    }
    for name, value in mapping.items():
        monkeypatch.setattr(paths, name, value)
    return tmp_path


def hourly_series(start="2026-10-01", days=7, **constant):
    """Synthetic Open-Meteo hourly block with constant values unless overridden per hour."""
    from datetime import datetime, timedelta

    t0 = datetime.fromisoformat(start)
    times = [(t0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(24 * days)]
    base = {
        "wave_height": 0.5, "wave_direction": 180, "swell_wave_height": 0.3, "swell_wave_period": 6.0,
        "swell_wave_direction": 180, "wind_wave_height": 0.3, "ocean_current_velocity": 0.5,
        "ocean_current_direction": 90, "wind_speed_10m": 5.0, "wind_direction_10m": 200, "wind_gusts_10m": 8.0,
    }
    base.update(constant)
    return {"time": times, **{k: [v] * len(times) for k, v in base.items()}}


def set_day(series, day_index, **values):
    for k, v in values.items():
        for h in range(day_index * 24, day_index * 24 + 24):
            series[k][h] = v
    return series
