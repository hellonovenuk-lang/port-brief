"""Port authority notices and carrier advisories, deduplicated against earlier runs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup

from port_brief import paths
from port_brief.config.feeds import FEEDS, GOOGLE_NEWS_RSS, RELEVANCE_KEYWORDS
from port_brief.sources.base import Context, SourceResult, http_get

LOOKBACK_DAYS = 7
MAX_PER_PUBLISHER = 6
SEEN_FILE = paths.ADVISORIES / "seen.json"
SEEN_LIMIT = 3000


def is_relevant(title: str) -> bool:
    low = title.lower()
    return any(k in low for k in RELEVANCE_KEYWORDS)


def _hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _direct(ctx: Context, feed: dict) -> list[dict]:
    cfg = feed["direct"]
    html = http_get(ctx, "advisories", cfg["url"]).text
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if cfg["link_contains"] not in href:
            continue
        url = cfg["base"] + href if href.startswith("/") else href
        text = a.get_text(" ", strip=True)
        if url in seen or len(text) < 15:
            continue
        seen.add(url)
        published = None
        if cfg.get("url_date_regex"):
            m = re.search(cfg["url_date_regex"], href)
            if m:
                published = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        if cfg.get("date_regex"):
            m = re.search(cfg["date_regex"], text)
            if m:
                published = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
                text = text[m.end():].strip()
        items.append({"title": text, "url": url, "published": published, "via": "direct"})
    return items


def _gnews(ctx: Context, feed: dict) -> list[dict]:
    q = f"{feed['gnews']} when:{LOOKBACK_DAYS}d"
    url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(q)}&hl=en-GB&gl=GB&ceid=GB:en"
    parsed = feedparser.parse(http_get(ctx, "advisories", url).text)
    items = []
    for e in parsed.entries:
        published = None
        if e.get("published"):
            try:
                published = parsedate_to_datetime(e.published)
            except (TypeError, ValueError):
                pass
        outlet = (e.get("source") or {}).get("title")
        title = e.title
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3]
        items.append({"title": title, "url": e.link, "published": published, "via": f"Google News / {outlet or 'unknown outlet'}"})
    return items


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(
        source="advisories",
        attribution="Headlines link to the original publishers; some discovered via Google News.",
        licence_note="Headlines and links only. Google News RSS terms are for personal use: review before charging subscribers.",
    )
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    cutoff = ctx.now - timedelta(days=LOOKBACK_DAYS)
    publishers, new_hashes, ok_count, urls = {}, [], 0, set()

    for feed in FEEDS:
        collected, errors = [], []
        for method in ("direct", "gnews"):
            if method == "direct" and not feed.get("direct"):
                continue
            try:
                collected += _direct(ctx, feed) if method == "direct" else _gnews(ctx, feed)
            except Exception as exc:
                errors.append(f"{method}: {exc}")
        if errors:
            result.errors += [f"{feed['id']} {e}" for e in errors]
        if collected or not errors:
            ok_count += 1

        items = []
        mentions = [m.lower() for m in feed.get("must_mention", [])]
        for it in sorted(collected, key=lambda i: i["published"] or cutoff, reverse=True):
            if it["url"] in urls or not is_relevant(it["title"]):
                continue
            if it["via"] != "direct" and mentions and not any(m in it["title"].lower() for m in mentions):
                continue
            if it["published"] and it["published"] < cutoff:
                continue
            urls.add(it["url"])
            h = _hash(it["url"])
            items.append({
                **it,
                "published": it["published"].strftime("%Y-%m-%d") if it["published"] else None,
                "is_new": h not in seen,
            })
            new_hashes.append(h)
            if len(items) >= MAX_PER_PUBLISHER:
                break
        publishers[feed["id"]] = {"name": feed["name"], "kind": feed["kind"], "items": items}

    if not ctx.dry_run:
        paths.ADVISORIES.mkdir(parents=True, exist_ok=True)
        merged = list(dict.fromkeys(list(seen) + new_hashes))[-SEEN_LIMIT:]
        SEEN_FILE.write_text(json.dumps(merged))

    result.status = "failed" if ok_count == 0 else ("partial" if result.errors else "ok")
    result.data = {"lookback_days": LOOKBACK_DAYS, "publishers": publishers}
    return result
