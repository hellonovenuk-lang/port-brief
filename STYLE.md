# Port Brief style rules

These rules are binding for every issue, every template change and every editorial the routine writes.
They exist because the patterns below make a document read as machine-made, and readers stop trusting it.

Most rules are enforced in code (`port_brief/editorial/slop.py`):
- `python -m port_brief validate` rejects editorial copy that breaks them.
- Rendering raises `SlopError` if the finished PDF HTML or the email does.

Don't work around a check. Change the copy or the design.

## Design

| Don't | Why | Do instead |
|---|---|---|
| Numbered sections or headings ("1 Port health") | Step-numbering for content that isn't a sequence | Plain sentence-case headings |
| Taglines under headings | Decoration that repeats the heading | Let the heading and content speak |
| Uppercase or eyebrow labels above headings | The commonest generated-design tell | Sentence case, weight for emphasis |
| Stat tiles, KPI rows, cards, rounded boxes, coloured card edges | Dashboard chrome, not a newsletter | Ruled tables, maps and short prose |
| Pill badges, glyph icons (▲ ◆), emoji, arrows (↑ ↓) | Visual noise that needs decoding | A small square plus the word; say trends in words |
| Middle-dot chains ("84% · 38 h") | Reads as a template filling fields | Commas and full stops |
| More than one colour system per page | Accent overload | Status colours for ports, severity colours for sea; everything else in ink |
| Dark backgrounds, gradients, shadows, glows | Generated-UI defaults | White page, one navy ink, hairline rules |

Functional hatch patterns, such as the "awaiting data" gauge and the print-safe severity fills, are allowed. They carry meaning.

## Writing

| Don't | Do instead |
|---|---|
| Em dashes | Full stop, comma or colon |
| "It's not X, it's Y", "X, not Y", "not just X but Y", "no X, no Y, just Z" | Say what it is |
| Rule of three: triplet lists or three-clause semicolon chains | One or two points; split long lines into sentences |
| "Label: instruction" repeated down a list ("Gusty Tue: allow 12 hours") | Plain sentences: the situation, then the action |
| Rhetorical questions, exclamation marks | Statements |
| Stock words and filler: delve, landscape, navigate, seamless, robust, pivotal, crucial, unprecedented, testament, underscore, "in today's", "it's worth noting", "to keep it that way", "in short" | The plain word, or nothing |
| Scene-setting openers, summing-up last lines | Start with the news; stop when it's said |

Every number must come from the data or the playbook. See ROUTINE.md.
