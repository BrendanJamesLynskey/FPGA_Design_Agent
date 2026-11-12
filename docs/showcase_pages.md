# Showcase pages: the template and its data contract

The site's **Showcase** section (`site/showcase.html` and one page per project at `showcase/<id>.html`) is built by
`site/showcase.py` from one YAML file per project in `site/showcase/`. A project adds its page by adding (or promoting)
its YAML file and committing the result files it points at; it does not write HTML or a new layout.

## A complete example

The smallest published entry, `site/showcase/<id>.yaml` (a fuller one, with every field, is
`site/tests/fixtures/showcase/demo_hist.yaml`):

```yaml
id: debug_in_words
status: published
title: Debugging in plain English
one_line: Ask for a capture in words and get the waveform and a plain answer back.
board: Digilent Nexys A7-100T
part: xc7a100tcsg324-1
values:                                   # every number on the page comes from here
  bytes: {source: results/debug_in_words/summary.json, expr: "get:capture.bytes"}
  runs:  {source: results/debug_in_words/runs/*.json, expr: n}
headline: "On the Digilent Nexys A7-100T (xc7a100tcsg324-1) the agent captured the {bytes} UART bytes asked for in words."
hero: {kind: wave, source: results/debug_in_words/hero.json, path: wave, caption: "The capture, replayed cycle by cycle."}
story:
  problem: "Setting up a logic analyser by hand is slow and easy to get wrong."
  how: "The request becomes signals chosen by RTL name and a trigger; the flow rebuilds, captures and reads the result."
  results: ["{runs} runs, each answered from a capture on the board."]
  agent: {request: "show me the UART byte when the FIFO overflows", plan: "...", gates: ["..."], approvals: ["..."]}
evidence:
  - {kind: record, label: Run records, path: results/debug_in_words/runs}
  - {kind: conditions, label: Die temperature and rails, path: results/debug_in_words/xadc.json}
  - {kind: versions, label: Tool versions and build ID, text: "not recorded"}
  - {kind: requirements, label: Requirements traced, text: "not recorded"}
limits: {not_measured: ["..."], nulls: [], next: ["..."]}
```

Common value expressions: `get:a.b.0.c` (the value at a path in the first file), `n` (how many files match the
glob), `count@rows:pass=true` (items of the list `rows` meeting a condition), `max@rows:latency_ns` (the largest value
at a path), `re:WNS=([-\d.]+)` (the first match in a text file). The full list: run
`python3 -c "import expertise; print(expertise.EXPR)"` from `site/`.

Build and check, as for every page:

```
FDA_FAMILY_MATRIX_KB=<knowledge-bank checkout> .venv/bin/python site/export.py   # writes site/data/showcase.json (the variable is needed only for the expertise data; maintainers have the checkout)
.venv/bin/python site/build.py && .venv/bin/python site/build.py --check
.venv/bin/python site/build.py --showcase-fixture site/tests/fixtures/showcase --out /tmp/preview   # the template with synthetic data
```

`site/export.py` refuses a file that breaks the contract with a `showcase.ContractError` that names the file and the
field, for example `x.yaml: headline: typed number(s) ['250']; use a {name} placeholder with a value expression`.
Projects are listed by status, then by `order` (default 99), then by title.

## Status

| `status` | Where it shows | Numbers allowed |
|---|---|---|
| `planned` | one line in the index's "Planned next" drawer | none |
| `in_progress` | a dashed card in "Being built now" | none |
| `published` | a card in "Measured on the board" and its own page | only through placeholders (below) |

A project moves to `published` when its first board result is committed. Until then the index shows no number for it.

## Fields

Every status: `id` (lower case, digits and `_`; the page name), `title`, `one_line`, optional `order` (index order).
`in_progress` adds `board`, optional `part`, and `what_it_will_show` (one sentence, no numbers).

`published` needs all of these:

| Field | What it is |
|---|---|
| `board`, `part` | the board and the exact part, for example `Digilent Nexys A7-100T`, `xc7a100tcsg324-1` |
| `vivado` | optional; defaults to `2026.1`, the only release published text may name |
| `values` | `name: {source: <repo path or glob>, expr: <value expression>}`; the expression forms are those of the expertise page (`python3 -c "import expertise; print(expertise.EXPR)"` in `site/`), for example `get:summary.p99_ns` or `count@rows:pass=true` |
| `headline` | the measured result in one plain sentence, naming the board and part, with `{name}` placeholders |
| `description` | optional page description (defaults to `one_line`) |
| `hero` | `{kind, source, path, caption}`: one of the graphics-kit kinds below, read from a committed JSON file at `path` inside it |
| `story.problem` | the problem, in plain words |
| `story.how` | how it works |
| `story.architecture` | optional diagram: `blocks: [[id, label], ...]` left to right, `links: [[from, to, label], ...]`; a link back or across two blocks is drawn under the row |
| `story.results` | a list of result sentences, every number a placeholder, uncertainty stated |
| `story.agent` | what the agent did: a mapping such as `request`, `plan`, `gates` (list), `approvals` (list) |
| `evidence` | a list of `{kind, label, path?, text?}`; `kind` is `record` (run records, raw captures), `conditions` (die temperature and rails against the recommended operating conditions), `versions` (tool versions, build ID), `requirements` (requirements traced). Every kind must appear at least once: write "not recorded" in `text` rather than leave one out. Paths must exist. |
| `limits` | `not_measured`, `nulls`, `next`: lists of sentences |
| `try_it` | optional `{command, note}` |

**No typed numbers.** In every text field, a number must come from a `{name}` placeholder. Names that look like numbers
(parts, boards, standards, the release) are allowed by the `PROSE_OK` pattern in `site/showcase.py`. `build.py --check`
then checks every number on the page against the project's data, as for every other page.

## Hero kinds (the shared graphics kit)

Each kind is drawn by `site/src/app.js` (`KIT`) from the JSON at `hero.source` / `hero.path`, inside the site's player
(play, step, scrub, speed, reset; arrow keys and space when focused; a live caption for screen readers). Under
`prefers-reduced-motion` nothing plays and the last frame, the whole result, is shown. Each is a 360-unit-wide SVG, so
it is legible at 390 px, and is capped at 640 px wide on desktop.

| `kind` | Data (normalised form) | What animates |
|---|---|---|
| `wave` | `{unit, x: [...], signals: [{name, kind: bit\|bus\|wave\|text, v: [...], radix?, width?, lo?, hi?}], captions?: [...]}`; every `v` has `len(x)` values | a cursor steps through the capture; the values at the cursor are listed beside it |
| `hist` | `{unit, label, bins, samples: [...], lo?, hi?, marks?: [{v, label}]}`; samples in the order recorded | the histogram accumulates the samples in order; the caption gives the count, median and largest so far |
| `shmoo` | `{x: {label, values}, y: {label, values}, unit?, points: [{x, y, v}]}`; `v` is `"pass"`, `0` (pass) or an error count; points in the order measured | the grid fills point by point; pass is a filled cell, fail an outlined one (not colour alone) |

The project's own export (in its `results/` folder) writes this normalised JSON from its raw captures and commits it.

## Tests

`site/tests/test_showcase.py` checks: the contract (typed numbers, missing evidence kinds and off-grid points are
refused), that in-progress projects show no numbers, that the fixture pages render with their hero data inlined and
pass the number check, and that the kit's code handles each kind. `site/tests/e2e_showcase.js` (puppeteer, run
locally under a heavy slot) loads each fixture page at 390 and 1280 px, light and dark, and fails on a console error,
horizontal overflow, or a hero that draws nothing.

## Portfolio card

Each published project can add an entry to `site/portfolio/portfolio.json` in the same shape as the main entry: a
title, one sentence, three facts each with its `source` in `site/data`, a still and a short silent animation recorded
from the page's own hero, and the canonical URL.
