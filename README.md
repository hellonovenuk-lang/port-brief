# Port Brief

A twice-weekly freight intelligence brief for UK freight forwarders, importers and logistics managers.
It goes out Monday and Thursday at 07:00 UK as a short email linking to a PDF.

Small importer teams get everything in one place, with **a status and a concrete action for every port**:
- the UK four: Felixstowe, Southampton, London Gateway and Liverpool
- the North European hubs: Rotterdam, Antwerp, Bremerhaven and Hamburg

For example: *"Felixstowe: congested, 13 pp above normal. Add 2–3 days to inland plans for containers
arriving in the next 2 weeks."* The brief also covers weather on the routes in ("On the way in"),
schedule reliability, and port and carrier advisories.

Samples:
- [`samples/2026-10-12/`](samples/2026-10-12/): a real issue from live data.
- [`samples/illustration/`](samples/illustration/): synthetic inputs showing every port status.

## How it runs

```
Mon & Thu 05:50 UK   Claude Code Routine (scheduled cloud session) follows ROUTINE.md:
                       collect → judge → [read Xeneta image if new] → draft → write editorial → validate → render
                       → opens PR "Port Brief · <date>: <headline>" with the PDF, a preview and a check list
You                  review the PR on GitHub (or the GitHub mobile app)
                       Merge   = approve → publish.yml deploys the PDF to Netlify and sends via Resend
                       Close   = reject  → nothing is sent
                       Comment = changes → the session edits, re-validates and re-renders on the same PR
```

- **Scripts do all the data work.** Claude does only two things: it writes the prose, and it reads
  Xeneta's carrier table, which is published only as an image.
- **Every number in the prose is checked against the data.** `validate` rejects any figure that no
  snapshot value rounds to. If the prose fails, a templated version is used, so an issue is always produced.
- **Merging the PR is the only way anything is sent.** `publish.yml` also refuses issues more than
  two days old, so a stale forecast can't be sent by merging an old PR.

## Sources

| Source | What | Access | Cadence | Failure mode |
|---|---|---|---|---|
| Open-Meteo Marine + Forecast | Wave, swell, wind-wave height, swell period/direction, current, wind, gusts. 8 ports + 14 lanes, 7 days hourly | No key | Every run | `partial`/`failed`; issue shows no weather |
| Open-Meteo Marine (storm field) | Daily peak wave height on a 3–4° grid of about 1,200 sea points along the routes into Europe | No key | Every run | No shading on the map; the key still lists flagged lanes |
| GDACS | Active tropical cyclones, distance to each port/lane | No key | Every run | Cyclone panel empty |
| Sinay Congestion API v1 | Berth occupancy %, gap vs the port's mean, time in port, vessels in port. One batch call for all 8 ports | `SINAY_API_KEY` | Every run | `skipped` (no key) or `failed`; column shows n/a |
| Sea-Intelligence GLP | Global reliability series + top-13 carriers, parsed from the `.xlsx` attached to each press release | No key | Monthly, ~4 weeks lag | Last good month reused, marked stale |
| Xeneta Scorecard | Global % from text; carrier table read from image by Claude, cross-checked against carriers quoted in the text | No key | Monthly, ~2 weeks lag | Previous month used until extracted |
| Advisories | All 8 ports; Maersk, MSC, Hapag-Lloyd, CMA CGM. Official site where it allows scripted access (Rotterdam, Maersk), otherwise Google News RSS | No key | Every run (7-day window) | Per-publisher; others unaffected |

Felixstowe, ABP, MSC, Hapag-Lloyd and CMA CGM return 403 to scripted requests, which is why Google News
is the fallback. Selectors and queries live in `port_brief/config/feeds.py`.

Sea-Intelligence and Xeneta are stored and shown **separately**. The gap between them is editorial
material, not an error to reconcile. Sea-Intelligence counts an arrival as on time if it is within one day
of schedule; Xeneta counts only arrivals on the scheduled day.

## Design

The issue is set as a broadsheet briefing: a white A4 page, Source Serif 4 for text and Source Sans 3 for
tables and captions (both OFL, bundled), one navy ink for the masthead, and status colours only as small
squares beside the status word.

The layout avoids the common tells of machine-made design: dark dashboards, stat tiles, cards with
coloured edges, pill badges, uppercase eyebrow labels, gradients and glyph icons.

Each issue runs in three parts, built to be read at a glance:

1. **Port health check** (page 1). The headline, a three-line summary and the North European ports map coloured by status, then one row per port:
   - the status;
   - a **congestion gauge**: berth occupancy against the port's normal level, from Sinay; it shows "awaiting data" until `SINAY_API_KEY` is set;
   - median time in port with a trend arrow;
   - **seven day squares** for crane weather;
   - one short action.
2. **Weather on the way in** (page 2).
   - **Storm map**: the six-day peak sea state shaded where Rough, Severe or Extreme, numbered.
   - **Route strips**: one row per trade route into the UK (Asia via the Cape, Asia via Suez, US East Coast, Caribbean, Mediterranean, West Africa, North Sea feeders). Each is a chain of sea areas coloured by severity, with the expected delay at the end. Routes are defined in `config/routes.py`.
   - A compact numbered key.
3. **News and notices** (page 3). Ports and shipping lines in two columns. Each notice is tagged Disruption, Surcharge, Service change or Other (`editorial/tags.py`). A compact line-reliability chart and sources sit below.

Calm areas are not shaded or named. A quiet week shows a clear map and all-grey route strips.

**[STYLE.md](STYLE.md) is binding.** Its rules are enforced by `port_brief/editorial/slop.py`: `validate` rejects editorial copy that breaks them, and rendering fails if the finished PDF or email does. The writing is checked as well as the numbers. `validate` rejects em dashes, "it's not X, it's Y",
rhetorical questions and similar machine-writing tics (`STYLE_RULES` in `editorial/schema.py`).

## Architecture

```
port_brief/
  sources/        one module per source; each returns the same SourceResult shape
  collect.py      orchestrator: runs every source in isolation, writes one snapshot per run
  judgement/      weather → operational flags, 3–5 day outlook, forecast drift, ranked watchlist
  editorial/      facts sheet, editorial schema, number validator, templated fallback
  render/         WeasyPrint PDF, email HTML/text, matplotlib charts and maps, bundled Source Serif/Sans fonts
  publish/        Netlify site build + Resend send (used only by publish.yml)
data/             committed history (each routine run starts in a fresh container)
  snapshots/      <run>.json + latest.json: consolidated snapshot incl. judgement and source health
  history/        weather/<run>.json (hourly series, for change over time), congestion/<run>.json
  reliability/    sea_intelligence/latest.json, xeneta/<period>.json (+ image and article text)
  advisories/     seen.json (dedup, so "NEW" means not in a previous issue)
  logs/fetch.jsonl  every fetch: timestamp, URL, status, duration, success/failure
drafts/<date>/    the issue: snapshot.json, facts.md, editorial.json, PDF, email.html/.txt, preview.png
```

Every source returns `{source, status: ok|partial|failed|skipped|stale, fetched_at, duration_ms,
attribution, licence_note, errors[], data}`. `run_source()` catches everything, so one source failing
never breaks the run.

## Commands

```bash
pip install -r requirements.txt

python -m port_brief collect                 # live fetch of all sources → data/snapshots/<run>.json
python -m port_brief collect --only advisories schedule_reliability   # re-run some sources into latest snapshot
python -m port_brief judge                   # add judgement to latest snapshot
python -m port_brief draft                   # facts.md + editorial (fallback if none) + PDF/email
python -m port_brief validate --date 2026-10-01
python -m port_brief render --date 2026-10-01
python -m port_brief all                     # collect + judge + draft

python -m port_brief all --dry-run           # everything from data/cache: no network, output under */dry-run/
python -m pytest -q
```

Dry-run replays the responses cached by the last live run in that checkout. `data/cache/` is
gitignored, so do one live run before iterating offline.

## Port status and actions (`port_brief/config/playbook.py`)

Each port gets one status. The worst signal wins:

| Status | Triggered by | Action given |
|---|---|---|
| ◆ Disruption likely | Crane or pilotage limits exceeded (window shown in UK time), or a strike, closure or cyber headline naming the port | Tell your haulier to expect longer waits; allow 24–48 hours around the window |
| ■ Congested | Sinay berth occupancy ≥ 10 pp above the port's normal, or median time in port ≥ 25% above our trailing average | Add 2–3 days to inland plans for containers arriving in the next 2 weeks; pre-book haulage; check free time and demurrage |
| ▲ Watch | Near crane or pilotage limits, occupancy 5–10 pp above normal, or a congestion headline | Allow 12–24 hours; avoid tight cut-offs |
| ● Running normally | Nothing flagged | Speak to your carrier about release and delivery now |

- If Sinay data is missing, the issue says so. The status then rests on weather and news only, and it never claims congestion is normal.
- Lanes feed "On the way in": watch means up to 1 day late, likely means 1–2 days, for the named trades.
- Every number in these actions lives in the playbook, and the validator only accepts those numbers.

## Judgement thresholds

These are starting heuristics, not published standards. They're set in
`port_brief/config/locations.py` and can be overridden per location with a `thresholds` key.

| Flag | Watch | Likely | Why |
|---|---|---|---|
| Crane (ports) | gust ≥ 15 m/s or wind ≥ 13 m/s | gust ≥ 20 m/s or wind ≥ 17 m/s | STS cranes typically stop around 20 m/s at boom height; 10 m model winds under-read that, so gusts lead |
| Pilot boarding (ports) | sea ≥ 2.5 m, or swell ≥ 1.5 m at ≥ 10 s | sea ≥ 3.5 m, or swell ≥ 2.5 m at ≥ 12 s | Boarding is suspended in heavy sea or long-period swell |
| Heavy weather (lanes) | sea ≥ 4 m or wind ≥ 17.2 m/s (F8) | sea ≥ 6 m or wind ≥ 20.8 m/s (F9); **extreme** from 8 m or 24.5 m/s (F10) | Speed loss and routing |
| Agulhas | SW swell (200–260°) with sea ≥ 4 m | …and running against the current | Abnormal-wave risk |
| Cyclone | within 1,200 km | within 500 km | GDACS current position |

- **Outlook**: the worst level in days 3–5 compared with days 0–1, giving `deteriorating`, `stable` or `improving`.
- **Drift**: compares the same target day with the previous run's forecast; it reports gust changes of 3 m/s or more and sea changes of 1 m or more.
- **Watchlist ranking**: level × trend × UK relevance (UK 1.5, North Europe 1.3, global 1.0).

## One-off setup

1. **Claude cloud environment** (environment settings): add the environment variable `SINAY_API_KEY`.
   Network access must allow the source hosts; all are reachable on the current setting.
2. **Resend**: verify your sending domain, then create a segment for subscribers.
3. **Netlify**: create a new site for the PDFs (separate from wardith.co.uk) and create a personal access token.
4. **GitHub repo → Settings → Secrets and variables → Actions**:
   - Secrets: `RESEND_API_KEY`, `RESEND_SEGMENT_ID`, `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`
   - Variables: `RESEND_FROM` (e.g. `Port Brief <brief@yourdomain.co.uk>`), `PDF_BASE_URL` (the Netlify
     site URL), `TEST_RECIPIENT` (your address), `PUBLISH_MODE` = `test`
5. Run one full test loop: the routine opens a PR, you merge it, and the test email arrives in your inbox.
   Then set `PUBLISH_MODE` = `broadcast`.
6. Optional: make the repo private. Merge-to-publish works the same way on a private repo.

## Licence and commercial items to revisit before charging subscribers

- **Open-Meteo**: the free API is **non-commercial only**. Move to a commercial plan (Standard,
  1M calls/month) before the newsletter is paid, or before it counts as commercial use.
  The data is **CC BY 4.0**: the attribution "Weather data by Open-Meteo.com (CC BY 4.0)" appears in every issue.
- **Sinay**: confirm your plan's terms allow republishing congestion figures in a paid newsletter.
  The free plan is about 500 calls/month and we use about 8–80.
- **Sea-Intelligence / Xeneta**: we quote publicly released headline figures with attribution and
  don't reproduce their charts or images. Keep it that way, and check each firm's terms before commercial use.
- **Google News RSS**: its terms are aimed at personal use. We show headlines and links only.
  Review before charging, or replace with carriers' own feeds where you have access.
- **GDACS**: attribute as European Commission JRC / UN OCHA (done in each issue).
- **Resend**: free up to 1,000 marketing contacts, then from $40/month for 5,000.
