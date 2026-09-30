"""Shared plumbing for every source: a uniform result, a crash-proof runner, and one HTTP
helper that logs each fetch and serves cached responses in dry-run mode."""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from port_brief import paths

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 PortBrief/1.0"
TIMEOUT = 30.0
RETRIES = 3


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Context:
    dry_run: bool = False
    now: datetime = field(default_factory=utcnow)


@dataclass
class SourceResult:
    source: str
    status: str = "ok"  # ok | partial | failed | skipped | stale
    fetched_at: str = ""
    duration_ms: int = 0
    attribution: str = ""
    licence_note: str = ""
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class FetchError(Exception):
    pass


def log_fetch(entry: dict) -> None:
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    with paths.FETCH_LOG.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _cache_path(source: str, method: str, url: str, params: dict | None, body: Any) -> "paths.Path":
    key = json.dumps([method, url, params or {}, body], sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return paths.CACHE / source / f"{digest}.json"


def http_get(
    ctx: Context,
    source: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    method: str = "GET",
    json_body: Any = None,
    binary: bool = False,
) -> httpx.Response | "CachedResponse":
    """Fetch a URL, logging the attempt. Live runs write the response to the cache;
    dry runs read from it and never touch the network."""
    cache_file = _cache_path(source, method, url, params, json_body)
    started = time.monotonic()
    entry = {"ts": iso(utcnow()), "source": source, "url": url, "method": method, "dry_run": ctx.dry_run}

    if ctx.dry_run:
        if not cache_file.exists():
            entry.update(ok=False, error="no cached response")
            log_fetch(entry)
            raise FetchError(f"dry-run: no cached response for {url}")
        cached = CachedResponse.load(cache_file)
        entry.update(ok=True, http_status=cached.status_code, cached=True)
        log_fetch(entry)
        return cached

    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    resp = None
    for attempt in range(RETRIES):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.request(method, url, params=params, headers=hdrs, json=json_body)
            if resp.status_code < 500 and resp.status_code != 429:
                break
        except httpx.HTTPError as exc:
            if attempt == RETRIES - 1:
                entry.update(ok=False, error=f"{type(exc).__name__}: {exc}", attempts=attempt + 1,
                             duration_ms=int((time.monotonic() - started) * 1000))
                log_fetch(entry)
                raise FetchError(f"{url}: {type(exc).__name__}: {exc}") from exc
        time.sleep(2 ** (attempt + 1))
    entry["attempts"] = attempt + 1

    duration = int((time.monotonic() - started) * 1000)
    ok = resp.is_success
    entry.update(ok=ok, http_status=resp.status_code, duration_ms=duration)
    if not ok:
        entry["error"] = resp.text[:200]
    log_fetch(entry)
    if not ok:
        raise FetchError(f"{url}: HTTP {resp.status_code}")
    CachedResponse.store(cache_file, resp, binary)
    return resp


class CachedResponse:
    def __init__(self, status_code: int, text: str, content: bytes, headers: dict):
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers

    def json(self) -> Any:
        return json.loads(self.text)

    @staticmethod
    def store(path, resp: httpx.Response, binary: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": resp.status_code, "headers": dict(resp.headers), "url": str(resp.url)}
        if binary:
            payload["hex"] = resp.content.hex()
        else:
            payload["text"] = resp.text
        path.write_text(json.dumps(payload))

    @classmethod
    def load(cls, path) -> "CachedResponse":
        payload = json.loads(path.read_text())
        if "hex" in payload:
            content = bytes.fromhex(payload["hex"])
            text = ""
        else:
            text = payload["text"]
            content = text.encode()
        return cls(payload["status"], text, content, payload.get("headers", {}))


def run_source(name: str, fn: Callable[[Context], SourceResult], ctx: Context) -> SourceResult:
    """Run one source. Whatever happens inside, a SourceResult comes back."""
    started = time.monotonic()
    try:
        result = fn(ctx)
    except Exception as exc:  # a source must never break the run
        result = SourceResult(source=name, status="failed", errors=[f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=3)])
    result.source = name
    result.fetched_at = result.fetched_at or iso(ctx.now)
    result.duration_ms = int((time.monotonic() - started) * 1000)
    log_fetch({"ts": iso(utcnow()), "source": name, "event": "source_complete", "status": result.status, "errors": result.errors[:1], "duration_ms": result.duration_ms})
    return result
