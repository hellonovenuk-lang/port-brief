"""Trade routes into the UK, as chains of sea areas from origin to the Channel.

Each id is a tracked lane (config/locations.py) or a named area from the storm-field
gazetteer (judgement/storm_areas.py, ids "area-<name>"). The route strip in part 2 colours each
segment by this week's severity, and the route's expected delay comes from its worst segment.
"""

ROUTES = [
    {"id": "asia_cape", "name": "Asia via the Cape",
     "segments": ["area-south-china-sea", "malacca", "sri_lanka", "area-western-indian-ocean", "agulhas",
                  "area-off-namibia", "area-off-west-africa", "area-off-portugal", "biscay", "western_approaches", "dover_strait"]},
    {"id": "asia_suez", "name": "Asia via Suez",
     "segments": ["area-south-china-sea", "malacca", "sri_lanka", "arabian_sea", "bab_el_mandeb", "area-red-sea",
                  "suez", "area-mediterranean", "gibraltar", "area-off-portugal", "biscay", "dover_strait"]},
    {"id": "us_east", "name": "US East Coast and Canada",
     "segments": ["area-north-west-atlantic", "mid_north_atlantic", "western_approaches", "dover_strait"]},
    {"id": "caribbean", "name": "Caribbean and Panama",
     "segments": ["panama", "area-caribbean", "area-azores", "western_approaches", "dover_strait"]},
    {"id": "med", "name": "Mediterranean",
     "segments": ["area-mediterranean", "gibraltar", "area-off-portugal", "biscay", "dover_strait"]},
    {"id": "west_africa", "name": "West Africa",
     "segments": ["area-gulf-of-guinea", "area-off-west-africa", "area-off-portugal", "biscay", "western_approaches", "dover_strait"]},
    {"id": "north_sea", "name": "North Sea feeders",
     "segments": ["area-north-sea", "german_bight", "dover_strait"]},
]

# Short names for the strip segments (full names appear in the map key).
SEGMENT_SHORT = {
    "area-south-china-sea": "S China Sea", "malacca": "Malacca", "sri_lanka": "Sri Lanka",
    "area-western-indian-ocean": "Indian Ocean", "agulhas": "Cape", "area-off-namibia": "Namibia",
    "area-off-west-africa": "W Africa", "area-off-portugal": "Portugal", "biscay": "Biscay",
    "western_approaches": "W Approaches", "dover_strait": "Dover", "arabian_sea": "Arabian Sea",
    "bab_el_mandeb": "Aden", "area-red-sea": "Red Sea", "suez": "Suez", "area-mediterranean": "Med",
    "gibraltar": "Gibraltar", "area-north-west-atlantic": "NW Atlantic", "mid_north_atlantic": "Mid-Atlantic",
    "panama": "Panama", "area-caribbean": "Caribbean", "area-azores": "Azores",
    "area-gulf-of-guinea": "G of Guinea", "area-north-sea": "North Sea", "german_bight": "German Bight",
}
