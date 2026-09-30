from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
DRY_RUN_SNAPSHOTS = SNAPSHOTS / "dry-run"
WEATHER_HISTORY = DATA / "history" / "weather"
CONGESTION_HISTORY = DATA / "history" / "congestion"
RELIABILITY = DATA / "reliability"
ADVISORIES = DATA / "advisories"
CACHE = DATA / "cache"
LOGS = DATA / "logs"
FETCH_LOG = LOGS / "fetch.jsonl"
DRAFTS = ROOT / "drafts"
