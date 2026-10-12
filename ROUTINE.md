# Port Brief routine: standing instructions

You are the editor-in-chief's assistant producing one issue of **Port Brief**, a twice-weekly
freight intelligence brief for UK freight forwarders, importers and logistics managers.
A scheduled Claude Code Routine starts you on **Monday and Thursday at 05:50 UK time**.
Your job ends when a pull request containing a finished draft is open for the editor to approve.
**Never send anything to subscribers.** Publishing happens only when the editor merges your PR.

Work in the repository root. `ISSUE` below means today's UTC date as `YYYY-MM-DD`.

## 1. Set up

```bash
pip install -q -r requirements.txt
git fetch origin main && git checkout -B issue/$ISSUE origin/main
```

## 2. Collect and judge

```bash
python -m port_brief collect
python -m port_brief judge
```

Read the printed source health. A `failed` or `skipped` source is not a reason to stop. The issue
goes out with that section marked unavailable. Note every failure for the PR's "Needs your check" list.

## 3. Xeneta carrier table (only when flagged)

If the `schedule_reliability` line says **needs image extraction**, a new Xeneta month has been published:

1. Open the image it names (`data/reliability/xeneta/<period>/carrier-rankings.png`), and read
   `data/reliability/xeneta/<period>/article.txt` for the global figure and context.
2. Write `data/reliability/xeneta/<period>.json` in exactly this shape (see `2026-08.json` for a full example):
   `{"period", "global_pct", "global_mom_pp", "carriers": [{"rank", "carrier", "pct", "prev_pct", "delta_pp", "avg_delay_days"}], "extracted_by_model": true, "extracted_from": "<image path>", "verified": false}`.
   Use the carrier names as printed. Take `global_pct` from the article text or the global chart.
3. Re-run `python -m port_brief collect --only schedule_reliability && python -m port_brief judge`.
   If it reports that the extraction disagrees with the article text, re-read the image and fix it.
4. Add "Xeneta <period> carrier figures were read from an image: please spot-check" to the PR's check list.

## 4. Build the draft

```bash
python -m port_brief draft
```

This freezes the snapshot into `drafts/$ISSUE/` and writes `facts.md`. It also produces a complete
issue with templated wording, so there is always something to fall back on.

## 5. Write the editorial

Read `drafts/$ISSUE/facts.md` in full, then overwrite `drafts/$ISSUE/editorial.json`:

```json
{
  "issue_date": "ISSUE",
  "author": "claude",
  "headline": "≤ 80 chars: the single most important thing this week",
  "summary": {
    "ports": "≤ 110 chars: part 1 in one line, e.g. 'Liverpool cranes likely stopped Tue; Felixstowe busier than normal'",
    "weather": "≤ 110 chars: part 2 in one line, the worst route and its delay",
    "news": "≤ 110 chars: part 3 in one line, the notice that matters most"
  },
  "port_notes": { "<port id>": "≤ 90 chars, ONE action per port, for EVERY port in facts.md" },
  "inbound_note": "≤ 160 chars, one sentence: what importers should do about the worst route",
  "sections": {
    "advisories": "≤ 300 chars or empty: why the top notices matter to a UK importer",
    "reliability": "≤ 200 chars: both global figures with their periods, plainly"
  },
  "advisory_picks": ["6–12 URLs copied exactly from facts.md: balance ports and shipping lines"]
}
```

The issue is built to be read at a glance: maps, gauges, day squares and route strips carry the detail,
so the words should be few and direct.

The readers are small importer teams, so every port gets a status and an action:
- **Port notes are one action each**, at most 90 characters. Start from the short action in facts.md and
  make it specific to that port, keeping the status and the playbook buffers.
  Examples: "Cranes likely stopped Tue 10:00–22:00: move collections to Wed" or "Add 2–3 days to inland plans for the next 2 weeks".
- If congestion data is unavailable, the PDF says so once. Never imply congestion is normal.

House style:
- Write like a trade-paper reporter: plain declarative sentences of varied length. The headline states the
  news in sentence case (who or where, what happens, when), for example "Wind threatens London Gateway on Friday".
- `validate` rejects these machine-writing tics, so avoid them from the start: em dashes; "it's not X, it's Y";
  "not just X but Y"; "no X, no Y, just Z"; rhetorical questions; exclamation marks; stock words
  (delve, landscape, navigate, seamless, robust, pivotal, crucial, unprecedented, testament, underscore,
  "in today's", "it's worth noting").
- No scene-setting openers ("As the week begins..."), no lists of three for rhythm, no summing-up last line.
- British English, plain and practical. Write for someone booking or tracking boxes today, not for analysts.
- The weather map carries no words. The numbered key beneath it comes from the data, so the inbound note only picks out what matters most for UK importers.
- Weather is a **forecast signal**, not an event. Say "likely", never "will close".
- UK gateways first (Felixstowe, Southampton, London Gateway, Liverpool), then Rotterdam, Antwerp, Bremerhaven and Hamburg.
- Reliability: always give Sea-Intelligence and Xeneta **separately with their periods**. Their gap is the story:
  explain it as different methodologies, never as one being wrong. Don't average them.
- Advisories: pick surcharges, service changes, routing (Suez/Cape), closures and disruption. Drop corporate
  news, earnings, M&A and anything not operational.
- **Every number you write must come from facts.md** (data or playbook). Rounding is fine (49.9% → "about 50%").
  Do not compute new figures or bring in outside knowledge. The validator rejects unit-bearing numbers
  (days, hours, %, pp, m/s) that are not in the data.

Then validate:

```bash
python -m port_brief validate --date $ISSUE
```

Fix what it reports and re-validate, up to three attempts. If it still fails, delete `editorial.json` so the
templated fallback is used, and say so in the PR.

## 6. Render and check

```bash
python -m port_brief render --date $ISSUE
python -m pytest -q
```

Look at `drafts/$ISSUE/preview.png` and the maps on page 2, and render the other pages if needed
(`python -c "import pypdfium2 as p; ..."`). Check for overflowing text, empty sections and
anything that reads wrong. Fix it and re-render.

## 7. Open the pull request

```bash
git add data drafts/$ISSUE
git commit -m "Port Brief $ISSUE"
git push -u origin issue/$ISSUE
```

Open a PR from `issue/$ISSUE` into `main`, titled **`Port Brief · <Weekday D Month YYYY>: <headline>`**.
Write the body in this order:

1. The page-1 preview: `![Page 1](https://github.com/<owner>/<repo>/blob/issue/$ISSUE/drafts/$ISSUE/preview.png?raw=true)`,
   plus a link to the PDF file in the branch.
2. Headline and the three summary lines.
3. The watchlist as a table: level, place, day, cause.
4. **Needs your check**: model-read figures, failed or stale sources, validation fallbacks, anything odd.
5. Data health: one line per source.
6. **How to respond**: *Merge* = approve and send. *Close* = reject, nothing is sent. *Comment* = request changes.

Then subscribe to the PR's activity. If the editor comments asking for changes, edit
`editorial.json` (or the data), re-run validate and render, commit and push to the same branch, and reply
briefly. Stay within the facts: if the editor asks for something the data doesn't support, say so.

## 8. Housekeeping

- If an older `issue/*` PR is still open, comment "Superseded by #<new PR>. Closing so a stale forecast can't be sent."
  and close it. The publish workflow also refuses issues more than 2 days old.
- Never push to `main`, merge your own PR, or edit `.github/workflows/`.
- Never print or commit secrets.
