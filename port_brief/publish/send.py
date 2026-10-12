"""Publish an approved issue. Called only by .github/workflows/publish.yml after an issue PR
is merged (merging the PR is the editor's approval).

    python -m port_brief.publish.send site              # build site/ with every approved PDF
    python -m port_brief.publish.send email --date D    # send the issue (test or broadcast mode)

Environment:
    PUBLISH_MODE      "test" (default: one email to TEST_RECIPIENT) or "broadcast" (all subscribers)
    RESEND_API_KEY    secret
    RESEND_SEGMENT_ID secret, broadcast mode only
    RESEND_FROM       e.g. "Port Brief <brief@yourdomain.co.uk>" (domain verified in Resend)
    TEST_RECIPIENT    address for test mode
    PDF_BASE_URL      e.g. https://port-brief-issues.netlify.app
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone

import httpx

from port_brief import paths
from port_brief.render.issue import email_subject

RESEND_API = "https://api.resend.com"
SITE = paths.ROOT / "site"
MAX_AGE_DAYS = 2  # never send a stale forecast by merging an old PR


def issue_dirs():
    for d in sorted(paths.DRAFTS.glob("20*-*-*")):
        if (d / "meta.json").exists() and list(d.glob("port-brief-*.pdf")):
            yield d


def pdf_path_for(d) -> str:
    meta = json.loads((d / "meta.json").read_text())
    return f"issues/{meta['issue_date']}-{meta['pdf_token']}.pdf"


def build_site() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "issues").mkdir(parents=True)
    count = 0
    for d in issue_dirs():
        shutil.copy(next(d.glob("port-brief-*.pdf")), SITE / pdf_path_for(d))
        count += 1
    (SITE / "index.html").write_text("<!doctype html><meta charset=utf-8><title>Port Brief</title><p>Port Brief.</p>")
    (SITE / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (SITE / "_headers").write_text("/issues/*\n  X-Robots-Tag: noindex\n  Cache-Control: public, max-age=3600\n")
    print(f"site built with {count} issue PDF(s)")


def _resend(path: str, payload: dict, idempotency_key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    resp = httpx.post(f"{RESEND_API}{path}", json=payload, headers=headers, timeout=30)
    if not resp.is_success:
        raise SystemExit(f"Resend {path} failed: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


def send_email(issue_date: str) -> None:
    d = paths.DRAFTS / issue_date
    age = (datetime.now(timezone.utc).date() - date.fromisoformat(issue_date)).days
    if age > MAX_AGE_DAYS and os.environ.get("FORCE_SEND") != "1":
        raise SystemExit(f"issue {issue_date} is {age} days old; refusing to send a stale forecast (set FORCE_SEND=1 to override)")

    editorial = json.loads((d / "editorial.json").read_text())
    pdf_url = f"{os.environ['PDF_BASE_URL'].rstrip('/')}/{pdf_path_for(d)}"
    html = (d / "email.html").read_text().replace("{{PDF_URL}}", pdf_url)
    text = (d / "email.txt").read_text().replace("{{PDF_URL}}", pdf_url)
    subject = email_subject(editorial)
    sender = os.environ["RESEND_FROM"]
    mode = os.environ.get("PUBLISH_MODE", "test")

    # Check the PDF is live before telling anyone about it.
    head = httpx.get(pdf_url, timeout=30, follow_redirects=True)
    if head.status_code != 200:
        raise SystemExit(f"PDF not reachable at {pdf_url} (HTTP {head.status_code}); not sending")

    if mode == "broadcast":
        created = _resend("/broadcasts", {
            "segment_id": os.environ["RESEND_SEGMENT_ID"],
            "from": sender, "subject": subject, "html": html, "text": text,
            "name": f"Port Brief {issue_date}", "send": True,
        })
        print(f"broadcast sent: {created.get('id')} -> {pdf_url}")
    else:
        to = os.environ["TEST_RECIPIENT"]
        html = html.replace("{{{RESEND_UNSUBSCRIBE_URL}}}", "#")
        text = text.replace("{{{RESEND_UNSUBSCRIBE_URL}}}", "(unsubscribe link appears in the live broadcast)")
        sent = _resend("/emails", {"from": sender, "to": [to], "subject": f"[TEST] {subject}", "html": html, "text": text},
                       idempotency_key=f"port-brief-{issue_date}-test")
        print(f"test email sent to {to}: {sent.get('id')} -> {pdf_url}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="port_brief.publish.send")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("site")
    e = sub.add_parser("email")
    e.add_argument("--date", required=True)
    args = p.parse_args(argv)
    if args.cmd == "site":
        build_site()
    else:
        send_email(args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
