"""Schedule reliability from the two public monthly benchmarks, kept separate on purpose.

Sea-Intelligence (GLP): each press release links an .xlsx holding the global monthly series
and the top-13 carrier table, so everything here is parsed by script.

Xeneta (Schedule Reliability Scorecard): the carrier table is only published as an image.
The script finds the post, saves the image and the article text, and flags the period as
`needs_extraction`. The routine's Claude step reads the image and writes
data/reliability/xeneta/<period>.json. This module then cross-checks those figures
against every "Carrier (NN%)" mention in the article text.

The two methodologies differ widely. The gap is editorial material, not an error.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from port_brief import paths
from port_brief.sources.base import Context, SourceResult, http_get

SI_BASE = "https://www.sea-intelligence.com"
SI_PRESS_ROOM = f"{SI_BASE}/press-room"
XENETA_RSS = "https://www.xeneta.com/blog/rss.xml"
XENETA_BLOG = "https://www.xeneta.com/blog"

ATTRIBUTION = "Schedule reliability: Sea-Intelligence Global Liner Performance report; Xeneta Schedule Reliability Scorecard"

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def norm_carrier(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ---------------------------------------------------------------- Sea-Intelligence

def _si_latest_release(ctx: Context) -> tuple[str, str]:
    html = http_get(ctx, "schedule_reliability", SI_PRESS_ROOM).text
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select('a[href*="press-room/"]'):
        title = a.get_text(" ", strip=True)
        low = title.lower()
        if "global" in low and "reliab" in low:
            return title, SI_BASE + a["href"] if a["href"].startswith("/") else a["href"]
    raise ValueError("no global schedule reliability release found on press room page")


def parse_si_workbook(content: bytes) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    series_ws = wb[wb.sheetnames[0]]
    carriers_ws = wb[wb.sheetnames[1]]

    series = {}
    header = None
    for row in series_ws.iter_rows(values_only=True):
        if header is None and row and row[1] == "Jan":
            header = row
            continue
        if header and isinstance(row[0], int):
            for idx, month in enumerate(MONTH_ABBR, start=1):
                val = row[idx]
                if isinstance(val, (int, float)):
                    series[f"{row[0]}-{idx:02d}"] = round(val * 100, 1)

    rows = list(carriers_ws.iter_rows(values_only=True))
    period_dt = rows[0][1]
    if not isinstance(period_dt, datetime):
        raise ValueError(f"unexpected carrier sheet header: {rows[0]}")
    carriers = []
    for rank, row in enumerate((r for r in rows[1:] if r[0] and isinstance(r[1], (int, float))), start=1):
        carriers.append({"rank": rank, "carrier": str(row[0]).strip(), "pct": round(row[1] * 100, 1)})
    return {"period": period_dt.strftime("%Y-%m"), "series": series, "carriers": carriers}


def _prev_month(period: str, back: int) -> str:
    y, m = map(int, period.split("-"))
    m -= back
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def fetch_sea_intelligence(ctx: Context) -> dict:
    title, url = _si_latest_release(ctx)
    soup = BeautifulSoup(http_get(ctx, "schedule_reliability", url).text, "lxml")
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = "\n".join(p for p in paras if len(p) > 40 and "END OF PRESS RELEASE" not in p)
    xlsx = next((a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".xlsx")), None)
    if not xlsx:
        raise ValueError(f"no .xlsx attached to {url}")
    xlsx_url = SI_BASE + xlsx if xlsx.startswith("/") else xlsx
    wb = parse_si_workbook(http_get(ctx, "schedule_reliability", xlsx_url, binary=True).content)

    period = wb["period"]
    global_pct = wb["series"].get(period)
    prev, last_year = wb["series"].get(_prev_month(period, 1)), wb["series"].get(_prev_month(period, 12))
    delay = re.search(r"average delay for late vessel arrivals.{0,160}?to (\d+\.\d+) days", text, re.I | re.S)
    return {
        "source": "Sea-Intelligence",
        "methodology": "Share of vessel arrivals within one day of scheduled arrival; 34 trade lanes, 60+ carriers (GLP report).",
        "period": period,
        "global_pct": global_pct,
        "mom_pp": round(global_pct - prev, 1) if global_pct is not None and prev is not None else None,
        "yoy_pp": round(global_pct - last_year, 1) if global_pct is not None and last_year is not None else None,
        "avg_delay_late_days": float(delay.group(1)) if delay else None,
        "carriers": wb["carriers"],
        "series": wb["series"],
        "release_title": title,
        "release_url": url,
        "data_url": xlsx_url,
        "text": text,
        "extracted_by_model": False,
    }


# ---------------------------------------------------------------- Xeneta

def xeneta_period(title: str) -> str | None:
    low = title.lower()
    q = re.search(r"\bq([1-4])\s+(\d{4})", low)
    if q:
        return f"{q.group(2)}-Q{q.group(1)}"
    for name, num in MONTHS.items():
        m = re.search(rf"\b{name}\s+(\d{{4}})", low)
        if m:
            return f"{m.group(1)}-{num:02d}"
    return None


def xeneta_text_mentions(text: str) -> dict[str, int]:
    """Carrier figures quoted in prose, e.g. 'Maersk (51%)', used to check the image extraction."""
    mentions = {}
    for name, pct in re.findall(r"([A-Z][A-Za-z\-]+(?: [A-Z][A-Za-z\-]+)?) \((\d{1,3})%\)", text):
        mentions[norm_carrier(name)] = int(pct)
    return mentions


def _xeneta_dir():
    return paths.RELIABILITY / "xeneta"


def fetch_xeneta(ctx: Context) -> dict:
    feed = feedparser.parse(http_get(ctx, "schedule_reliability", XENETA_RSS).text)
    post = next((e for e in feed.entries if "schedule-reliability-scorecard" in e.link), None)
    if post is None:
        # The RSS only carries recent posts; the blog index keeps the scorecard linked for longer.
        soup = BeautifulSoup(http_get(ctx, "schedule_reliability", XENETA_BLOG).text, "lxml")
        link = next((a["href"] for a in soup.find_all("a", href=True) if "schedule-reliability-scorecard" in a["href"]), None)
        if link is None:
            raise ValueError("no Schedule Reliability Scorecard post in Xeneta RSS or blog index")
        title = link.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        post = feedparser.FeedParserDict(link=link, title=title)
    period = xeneta_period(post.title)
    if not period:
        raise ValueError(f"cannot read period from title {post.title!r}")

    soup = BeautifulSoup(http_get(ctx, "schedule_reliability", post.link).text, "lxml")
    article = soup.find("article") or soup
    text = "\n".join(
        t.get_text(" ", strip=True) for t in article.find_all(["h1", "h2", "h3", "p"])
        if len(t.get_text(strip=True)) > 30
    )
    images = {}
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        for key in ("carrier-rankings", "global-reliability"):
            if key in src and key not in images:
                images[key] = src

    out_dir = _xeneta_dir() / period
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = {}
    for key, src in images.items():
        try:
            src = re.sub(r"width=\d+", "width=1400", src).replace("&height=", "&h=")  # ~1/4 of full size, still legible
            resp = http_get(ctx, "schedule_reliability", src, binary=True)
            (out_dir / f"{key}.png").write_bytes(resp.content)
            saved[key] = str((out_dir / f"{key}.png").relative_to(paths.ROOT))
        except Exception:
            pass
    (out_dir / "article.txt").write_text(text)

    base = {
        "source": "Xeneta",
        "methodology": "Share of vessel arrivals on the scheduled day (eeSea data); Xeneta Ocean Benchmark.",
        "period": period,
        "release_title": post.title,
        "release_url": post.link,
        "published": post.get("published"),
        "images": saved,
        "text": text,
    }
    extraction_file = _xeneta_dir() / f"{period}.json"
    if not extraction_file.exists():
        return {**base, "needs_extraction": True, "global_pct": None, "carriers": []}

    extracted = json.loads(extraction_file.read_text())
    mentions = xeneta_text_mentions(text)
    checked, mismatches = [], []
    for c in extracted.get("carriers", []):
        key = norm_carrier(c["carrier"])
        # Prose may prefix names ("Partners Maersk (51%)"), so match on the end of the phrase.
        quoted = next((v for k, v in mentions.items() if k.endswith(key)), None)
        if quoted is None:
            continue
        checked.append(c["carrier"])
        if round(c["pct"]) != quoted:
            mismatches.append(f"{c['carrier']}: image {c['pct']}% vs text {quoted}%")
    global_in_text = extracted.get("global_pct") is not None and f"{round(extracted['global_pct'])}%" in text
    return {
        **base,
        **{k: v for k, v in extracted.items() if k not in ("text",)},
        "needs_extraction": False,
        "extracted_by_model": extracted.get("extracted_by_model", True),
        "verified": extracted.get("verified", False),
        "cross_check": {"checked_against_text": checked, "mismatches": mismatches, "global_pct_in_text": global_in_text},
    }


# ---------------------------------------------------------------- persistence and divergence

def _store(name: str, record: dict) -> None:
    folder = paths.RELIABILITY / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"latest.json").write_text(json.dumps(record, indent=2))


def _load_latest(name: str) -> dict | None:
    f = paths.RELIABILITY / name / "latest.json"
    return json.loads(f.read_text()) if f.exists() else None


def divergence(si: dict | None, xe: dict | None) -> dict | None:
    if not si or not xe or si.get("global_pct") is None or xe.get("global_pct") is None:
        return None
    if si["period"] != xe["period"]:
        return {"comparable": False, "note": f"Periods differ: Sea-Intelligence {si['period']}, Xeneta {xe['period']}."}
    xe_by = {norm_carrier(c["carrier"]): c for c in xe.get("carriers", [])}
    carriers = []
    for c in si.get("carriers", []):
        other = xe_by.get(norm_carrier(c["carrier"]))
        if other:
            carriers.append({
                "carrier": c["carrier"], "sea_intelligence_pct": c["pct"], "xeneta_pct": other["pct"],
                "gap_pp": round(c["pct"] - other["pct"], 1),
                "sea_intelligence_rank": c["rank"], "xeneta_rank": other.get("rank"),
            })
    return {
        "comparable": True,
        "period": si["period"],
        "global_gap_pp": round(si["global_pct"] - xe["global_pct"], 1),
        "carriers": carriers,
        "largest_gap": max(carriers, key=lambda c: abs(c["gap_pp"])) if carriers else None,
        "note": "Different definitions of 'on time' and different vessel samples; the gap is expected and is itself informative.",
    }


def fetch(ctx: Context) -> SourceResult:
    result = SourceResult(source="schedule_reliability", attribution=ATTRIBUTION)
    data = {}
    for name, fn in (("sea_intelligence", fetch_sea_intelligence), ("xeneta", fetch_xeneta)):
        try:
            record = fn(ctx)
            if not record.get("needs_extraction"):
                _store(name, record)
            data[name] = record
        except Exception as exc:
            result.errors.append(f"{name}: {exc}")
            cached = _load_latest(name)
            if cached:
                cached["stale_since"] = cached.get("stale_since") or ctx.now.strftime("%Y-%m-%d")
                data[name] = cached

    # A pending Xeneta extraction falls back to the last verified period for the issue.
    xe = data.get("xeneta")
    if xe and xe.get("needs_extraction"):
        result.errors.append(f"xeneta: {xe['period']} carrier table needs image extraction ({xe['images'].get('carrier-rankings')})")
        previous = _load_latest("xeneta")
        data["xeneta_pending"] = xe
        data["xeneta"] = previous
    if xe and xe.get("cross_check", {}).get("mismatches"):
        result.errors.append("xeneta: extraction disagrees with article text: " + "; ".join(xe["cross_check"]["mismatches"]))

    data["divergence"] = divergence(data.get("sea_intelligence"), data.get("xeneta"))
    if not data.get("sea_intelligence") and not data.get("xeneta"):
        result.status = "failed"
    elif result.errors:
        result.status = "partial"
    result.data = data
    return result
