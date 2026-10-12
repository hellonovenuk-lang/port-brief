import pytest

from port_brief.config.locations import BY_ID
from port_brief.editorial import schema
from port_brief.judgement import storm_areas
from port_brief.render import worldmap
from port_brief.sources import storm_field


def test_topojson_land_decodes_without_antimeridian_streaks():
    rings = worldmap.land_rings("110m")
    assert len(rings) > 100
    for r in rings:
        xs = [p[0] for p in r]
        # unwrapped rings never jump half way round the world between neighbouring points
        assert all(abs(a - b) < 180 for a, b in zip(xs, xs[1:]))



def test_world_map_has_no_words_only_numbers(monkeypatch):
    import matplotlib.axes

    texts = []
    real_text = matplotlib.axes.Axes.text
    monkeypatch.setattr(matplotlib.axes.Axes, "text", lambda self, x, y, t, *a, **k: texts.append(t) or real_text(self, x, y, t, *a, **k))
    monkeypatch.setattr(matplotlib.axes.Axes, "annotate", lambda self, t, *a, **k: texts.append(t))
    field = [[lon, lat, 7.0 if (lon, lat) == (-30, 48) else 4.5, "2026-10-14"] for lon in range(-40, -19, 3) for lat in range(42, 55, 3)]
    items = worldmap.key_items(storm_areas.storm_areas(field), [], [])
    svg = worldmap.world_map(items, field)
    assert svg.startswith("<svg")
    assert texts and all(t.isdigit() for t in texts)


def test_europe_map_labels_every_port():
    ports = [{"id": pid, "name": BY_ID[pid]["name"], "status": "normal"} for pid in worldmap.PORT_MAP_COORDS]
    assert worldmap.north_europe_map(ports, [], []).startswith("<svg")


def test_storm_grid_excludes_land():
    pts = set(storm_field.grid_points())
    sahara = [(lon, lat) for lon, lat in pts if 0 <= lon <= 20 and 15 <= lat <= 28]
    assert sahara == []
    assert any(-35 < lon < -25 and 45 < lat < 50 for lon, lat in pts)  # open Atlantic present


def test_storm_areas_zone_and_severity():
    field = [[-30, 48, 8.4, "2026-10-14"], [-27, 48, 6.1, "2026-10-14"], [-6, 45.5, 4.2, "2026-10-15"],
             [-6, 48.5, 4.3, "2026-10-15"], [-60, 20, 3.0, "2026-10-13"]]
    areas = storm_areas.storm_areas(field)
    names = {a["name"]: a for a in areas}
    assert names["Mid-North Atlantic"]["severity"] == "Extreme"
    assert names["Mid-North Atlantic"]["delay"] == "2 days or more"
    assert all(a["peak_sea"] >= 4 for a in areas)  # calm cells never make a row


def test_extreme_lane_level():
    from conftest import hourly_series, set_day
    from port_brief.judgement import weather_risk as wr

    s = set_day(hourly_series(start="2026-10-12"), 3, wave_height=8.0)
    a = wr.assess_location(BY_ID["mid_north_atlantic"], s, [])
    assert a["days"][3]["level"] == "extreme"


@pytest.mark.parametrize("text", [
    "It's not a delay, it's a reset.",
    "Felixstowe is calm — for now.",
    "This is not just congestion but a backlog.",
    "No queues, no strikes, just calm.",
    "Why wait to book?",
    "Shippers must navigate a shifting landscape.",
    "Book now!",
])
def test_style_lint_catches_machine_tics(text):
    assert schema.style_issues(text)


def test_style_lint_allows_plain_advice():
    assert schema.style_issues("Felixstowe is congested. Add 2–3 days to inland plans and tell your haulier.") == []
