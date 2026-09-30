"""Port authority and carrier advisory feeds.

Each publisher tries its own site first (`direct`). Several sites (Felixstowe, ABP, MSC,
Hapag-Lloyd, CMA CGM) block scripted requests, so every publisher also has a Google News
RSS query as a fallback; Google News items must name the publisher in the headline
(`must_mention`). Selectors live here so a site redesign is a config fix.
"""

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

# Only operational items make the newsletter. Matched case-insensitively against titles.
RELEVANCE_KEYWORDS = [
    "advisory", "surcharge", "congestion", "disruption", "strike", "industrial action",
    "weather", "storm", "wind", "closure", "closed", "suspend", "delay", "service",
    "schedule", "rates", "rate increase", "gri", "pss", "fak", "peak season", "emergency",
    "suez", "red sea", "hormuz", "route", "rerout", "omission", "blank", "cape of good hope",
    "berth", "outage", "cyber", "canal", "tariff", "port call", "transit",
]

FEEDS = [
    {
        "id": "felixstowe", "must_mention": ["Felixstowe"], "name": "Port of Felixstowe", "kind": "port",
        "direct": None,  # 403 to scripted requests
        "gnews": '"Port of Felixstowe" OR "Felixstowe port"',
    },
    {
        "id": "liverpool", "must_mention": ["Liverpool", "Peel Ports"], "name": "Port of Liverpool (Peel Ports)", "kind": "port",
        "direct": None,
        "gnews": '"Port of Liverpool" OR "Peel Ports"',
    },
    {
        "id": "southampton", "must_mention": ["Southampton"], "name": "Port of Southampton (ABP)", "kind": "port",
        "direct": None,  # news list is rendered client-side
        "gnews": '"Port of Southampton" OR "Southampton container"',
    },
    {
        "id": "rotterdam", "must_mention": ["Rotterdam"], "name": "Port of Rotterdam", "kind": "port",
        "direct": {
            "type": "html",
            "url": "https://www.portofrotterdam.com/en/news-and-press-releases",
            "base": "https://www.portofrotterdam.com",
            "link_contains": "/en/news-and-press-releases/",
            "date_regex": r"(\d{1,2}) / (\d{1,2}) / (\d{4})",  # d / m / yyyy
        },
        "gnews": '"Port of Rotterdam"',
    },
    {
        "id": "maersk", "must_mention": ["Maersk"], "name": "Maersk", "kind": "carrier",
        "direct": {
            "type": "html",
            "url": "https://www.maersk.com/news",
            "base": "https://www.maersk.com",
            "link_contains": "/news/articles/",
            "url_date_regex": r"/(\d{4})/(\d{2})/(\d{2})/",
        },
        "gnews": '"Maersk" (advisory OR surcharge OR disruption OR service)',
    },
    {
        "id": "msc", "must_mention": ["MSC", "Mediterranean Shipping"], "name": "MSC", "kind": "carrier",
        "direct": None,
        "gnews": '"MSC" (shipping OR container OR surcharge OR advisory OR service)',
    },
    {
        "id": "hapag_lloyd", "must_mention": ["Hapag"], "name": "Hapag-Lloyd", "kind": "carrier",
        "direct": None,
        "gnews": '"Hapag-Lloyd"',
    },
    {
        "id": "cma_cgm", "must_mention": ["CMA CGM"], "name": "CMA CGM", "kind": "carrier",
        "direct": None,
        "gnews": '"CMA CGM"',
    },
]
