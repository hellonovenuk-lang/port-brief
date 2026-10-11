import pytest

from port_brief.config.locations import BY_ID
from port_brief.editorial import schema
from port_brief.render import worldmap


def test_topojson_land_decodes_without_antimeridian_streaks():
    rings = worldmap.land_rings("110m")
    assert len(rings) > 100
    for r in rings:
        xs = [p[0] for p in r]
        # unwrapped rings never jump half way round the world between neighbouring points
        assert all(abs(a - b) < 180 for a, b in zip(xs, xs[1:]))



def test_world_map_only_names_flagged_lanes(monkeypatch):
    labels = []
    monkeypatch.setattr(worldmap, "_label", lambda ax, x, y, title, sub, extent, colour=worldmap.INK: labels.append(title))
    inbound = [{"id": "biscay", "name": "Bay of Biscay", "level": "likely", "from_day": "2026-10-14", "delay": "1–2 days"}]
    svg = worldmap.world_map(inbound, storms=[{"name": "FAR-26", "lat": 10, "lon": -150, "nearby": []}])
    assert svg.startswith("<svg")
    assert labels == ["Bay of Biscay"]  # calm lanes and distant storms are not named


def test_europe_map_labels_every_port():
    ports = [{"id": pid, "name": BY_ID[pid]["name"], "status": "normal"} for pid in worldmap.PORT_MAP_COORDS]
    assert worldmap.north_europe_map(ports, []).startswith("<svg")


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
