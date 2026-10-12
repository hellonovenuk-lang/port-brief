"""The action playbook: how signals become a port status and advice for importers.

Every buffer and trigger lives here so it can be tuned without touching code. The editorial
validator whitelists these numbers, so Claude can quote them without being flagged.
"""

# Status order: the worst signal wins.
STATUS_ORDER = ["normal", "watch", "congested", "disruption"]
STATUS_LABEL = {
    "normal": "Running normally",
    "watch": "Watch",
    "congested": "Congested",
    "disruption": "Disruption likely",
}
# Status colours: used only as small markers beside the status word, never on their own.
STATUS_COLOUR = {"normal": "#2e7d32", "watch": "#b7791f", "congested": "#c4581d", "disruption": "#b3261e"}

# Congestion triggers (Sinay commercial-vessel occupancy, percentage points above that port's usual level).
CONGESTED_GAP_PP = 10.0
BUSY_GAP_PP = 5.0
# Our own history: median time in port this much above the trailing average also counts as congested.
CONGESTED_TIME_IN_PORT_PCT = 25.0

# Buffers quoted in the advice.
BUFFER = {
    "congested_days": "2–3 days",
    "congested_horizon": "the next 2 weeks",
    "disruption_hours": "24–48 hours",
    "watch_hours": "12–24 hours",
}

# Inbound lane delay estimates by weather level.
INBOUND_DELAY = {"watch": "up to 1 day", "likely": "1–2 days", "extreme": "2 days or more"}

# Route strips with no rough sea area on them.
NO_ROUTE_DELAY = "no weather delay"

# Rough areas away from the main lanes: only ships routed through them are affected.
OFF_ROUTE_DELAY = "only if routed through it"

# Sea-area severity on the weather map and in the delays key. Each step also has a hatch so the
# map separates them when printed in black and white.
SEVERITY_LABEL = {"watch": "Rough", "likely": "Severe", "extreme": "Extreme"}
SEVERITY_SEA_M = {"watch": 4.0, "likely": 6.0, "extreme": 8.0}
SEVERITY_COLOUR = {"watch": "#d9a441", "likely": "#d9762b", "extreme": "#b3261e"}
SEVERITY_HATCH = {"watch": None, "likely": "....", "extreme": "////"}

# Port headlines that change the status on their own (matched case-insensitively).
DISRUPTION_KEYWORDS = ["strike", "industrial action", "walkout", "closure", "closed", "shut", "cyber", "outage", "suspend"]
CONGESTION_KEYWORDS = ["congestion", "congested", "backlog", "delays", "yard full", "restrictions"]
# Headlines about the port's energy grid, roads or finances are not operational signals.
HEADLINE_EXCLUDE = ["grid", "electricity", "energy", "power", "road", "traffic jam", "profit", "revenue", "investment"]

ACTIONS = {
    "disruption_weather": (
        "Operations likely suspended {window}. Tell your haulier to expect longer waits and re-booked slots, "
        "and allow " + BUFFER["disruption_hours"] + " on collections and vessel arrivals around that window."
    ),
    "disruption_news": (
        "Reported disruption: {headline}. Check your terminal's latest notice before booking collections, "
        "and allow " + BUFFER["disruption_hours"] + "."
    ),
    "congested": (
        "Berths are busier than normal. Add " + BUFFER["congested_days"] + " to inland plans for containers arriving in "
        + BUFFER["congested_horizon"] + ", pre-book haulage and check free time and demurrage."
    ),
    "watch_weather": (
        "Intermittent stoppages possible {window}. Allow " + BUFFER["watch_hours"] + " and avoid tight cut-offs."
    ),
    "watch_news": "Reported: {headline}. Check your terminal's latest notice before booking collections.",
    "watch_busy": "Berths are busier than usual. Watch vessel berthing times and avoid tight cut-offs.",
    "normal": "No predicted delays. Speak to your carrier about release and delivery now.",
    "normal_no_congestion": "No weather disruption forecast. Speak to your carrier about release and delivery now.",
}

# One-line actions for the port rows: situation, then action, in plain sentences (90 characters or fewer).
SHORT_ACTIONS = {
    "disruption_weather": "Cranes likely stop {window}. Warn your haulier and allow " + BUFFER["disruption_hours"] + ".",
    "disruption_news": "Disruption reported. Check terminal notices and allow " + BUFFER["disruption_hours"] + ".",
    "congested": "Berths are busier than normal. Add " + BUFFER["congested_days"] + " to inland plans for " + BUFFER["congested_horizon"] + ".",
    "watch_weather": "Gusts near crane limits {window}. Allow " + BUFFER["watch_hours"] + ".",
    "watch_news": "Delays reported. Check terminal notices before booking.",
    "watch_busy": "Berths are busier than usual. Avoid tight cut-offs.",
    "normal": "No delays expected. Book release and delivery now.",
    "normal_no_congestion": "No weather delays forecast. Book release and delivery now.",
}

NO_CONGESTION_DATA = "Congestion data unavailable this issue; status based on weather and port news only."
