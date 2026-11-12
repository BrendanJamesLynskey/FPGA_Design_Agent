# Showcase pages: the template and its data contract

The site's **Showcase** section (`site/showcase.html` and one page per project at `showcase/<id>.html`) is built by
`site/showcase.py` from one YAML file per project in `site/showcase/`. A project adds its page by adding (or promoting)
its YAML file and committing the result files it points at; it does not write HTML or a new layout.

## A complete example

The smallest published entry, `site/showcase/<id>.yaml` (a fuller one, with every field, is
`site/tests/fixtures/showcase/demo_hist.yaml`, a synthetic fixture marked `fixture: true`). The paths below are
illustrative:

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
limits: {not_measured: ["..."], nulls: [], next: ["..."]}       # at least one not_measured (or null) and one next
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
| `story.problem` | the problem, in plain words; a blank line (`\n\n`) starts a new paragraph, here and in `story.how` |
| `story.how` | how it works |
| `story.architecture` | optional diagram: `blocks: [[id, label], ...]` left to right, `links: [[from, to, label], ...]`; a link back or across two blocks is drawn under the row |
| `story.results` | a list of result sentences, every number a placeholder, uncertainty stated |
| `story.agent` | what the agent did: a mapping such as `request`, `plan`, `gates` (list), `approvals` (list); the page shows these four in that order (the run's order), then any other keys |
| `story.table` | optional table read from a committed file: `{caption, source: results/..., path, columns: [[key, header], ...], link?: key holding a repo path, link_column?}`; the rows' numbers are data, so the number check accepts them; a boolean shows as yes or no and a missing value (null) as a blank cell, here and in every table the site builds |
| `story.results_table` | optional short table after the results list: `{caption, head: [...], rows: [[...], ...]}`; every cell is text with `{name}` placeholders, checked like the rest of the prose |
| `story.details` | optional short drawers after "What the agent did": `[{title, text}]`, numbers through placeholders |
| `evidence` | a list of `{kind, label, path?, text?}`; `kind` is `record` (run records, raw captures), `conditions` (die temperature and rails against the recommended operating conditions), `versions` (tool versions, build ID), `requirements` (requirements traced). Every kind must appear at least once: write "not recorded" in `text` rather than leave one out. Paths must exist. |
| `limits` | `not_measured`, `nulls`, `next`: lists of sentences. `nulls` are measured results with no effect (shown as "Measured, no effect found"); a request refused by design belongs in `not_measured` |
| `try_it` | optional `{command, note}` |

**What `site/export.py` refuses** (each raises `showcase.ContractError`):

- **Typed numbers anywhere in a published entry.** Every string, and every mapping key, is checked: title, one_line,
  headline, description, board, part, the hero caption, every story field (including architecture block and link
  labels and the agent mapping's keys and values), evidence labels and texts, limits and the try-it note. A number must
  come from a `{name}` placeholder. Names that look like numbers (AMD part names, boards, standards, Vivado 2026.1) are
  allowed by the `PROSE_OK` pattern in `site/showcase.py` (details below). Not checked as text: `values`, `hero.source`, `hero.path`,
  `evidence.path` and `try_it.command`.
- **For `in_progress` and `planned`:** any field outside the status's list, and any number in title, one_line, board,
  part or `what_it_will_show`.
- **For `published`:**
  - a `vivado` other than `2026.1`;
  - a hero whose `source` is not under `results/`;
  - empty `story.results` or `story.agent`;
  - `limits` without at least one `not_measured` (or `nulls`) item and one `next` item;
  - an evidence `record` without a path;
  - a missing evidence kind;
  - a path, value source or placeholder that does not resolve;
  - a hero kind the kit cannot draw, or hero data that does not fit its kind.
- **Synthetic fixtures** (`fixture: true`, hero data under `site/tests/`) are refused by the normal build. They build
  only with `--showcase-fixture`.

`build.py --check` then checks every number visible on a showcase page, and on the Showcase index, against the shared
site data (every `site/data/*.json` except the showcase data itself) plus the resolved `values` and hero data of the
published projects. The projects' own text is not part of that data, so a number typed into the YAML, including one in
the try-it command that the contract does not scan, fails the check unless the same number happens to occur elsewhere in
the site data. That is a weak backstop, since the shared data holds many small numbers; the contract's scan above is the
main guard. In that scan:
- any run of digits counts as a number, wherever it stands: after a letter, `#`, `.` or a hyphen, with a leading minus
  counted;
- only the names in `PROSE_OK` are exempt: AMD part names (`xc…`, matched as whole words), device families, boards,
  standards, Arm document numbers (`IHI 0022H`) and Vivado 2026.1;
- brief, PR, guide and rule numbers are not exempt.

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

**`wave` with stages (an option for any page).** Add `stages` to the wave data and the hero tells the run as a story:
a strip of the run's stages above the plot (the current one inverted, the done ones in full ink), then the samples
revealed one at a time while the `during` stage is lit, then the answer. Fields:

- `stages`: `[{name, fact, phase, captions}]` in order. `phase` is `before` (one frame per caption, nothing drawn yet),
  `during` (one frame per caption, then one frame per sample, revealed left to right; exactly one stage) or `after`
  (one frame per caption with everything drawn; at least one, so the last frame is the answer). `fact` is the short
  real number shown in the strip (for example the build time and ID).
- `captions` (per sample, optional; `null` entries get "cycle k: values" from the data): captions for the samples.
  Narrative steps go in the stages, not on sample cycles.
- `marks`: `[{x, label, signal?}]`: a vertical line at sample `x` (a trigger), or, with `signal`, a ring round that
  signal's change at `x`; each appears when the reveal reaches it, with its label under the plot.
- `tick` (the axis label step, in x units; labels sit at the centre of their sample), `alt` (a text alternative read
  by screen readers and the SVG's `<title>`: put the finding in it; the strip is a list and the caption is `aria-live`)
  and `key` (one line under the plot that says what the signal names mean).

Every `wave` hero, staged or not, is drawn as wide as its box (360 to 720 units) with text of 13 units, so its labels
stay about 12 to 13 px from a 390 px phone to a desktop and the plot uses the page's width. Below 520 units the signal
names sit above their traces, so the traces get the full width. A staged wave draws the whole capture faint while a
`before` stage is lit (never an empty grid), and sizes its time axis to the samples revealed so far (at least six). Mark
labels sit in a band above the axis, in two rows, with a vertical line down to the plot, so labels never overprint
(the e2e check fails on overlapping SVG text). Without `stages` a cursor
band steps through the samples and nothing is dimmed. Reduced motion shows the last frame (everything drawn, the answer stage lit). `site/showcase.py` checks the
phases, the caption count and that every mark is on the axis and names a signal of the hero.

The project's own export (in its `results/` folder) writes this normalised JSON from its raw captures and commits it.

## Tests

`site/tests/test_showcase.py` checks:
- the contract: every refusal above, including the 38-case probe from the PR #133 review;
- that in-progress projects show no numbers and get no page;
- that the fixture pages render with their hero data inlined and pass the number check;
- that the number check is not circular;
- that the kit's code handles each kind;
- the portfolio pack's sources;
- that the README's headline numbers match `site/data`.

`site/tests/e2e_render.js` (puppeteer) is run locally under a heavy slot. It sets `FDA_E2E=1` for
`test_e2e_pages_render_without_errors_or_overflow`, and is skipped in CI. It loads the main pages and each fixture page
at 390 and 1280 px, light and dark, with and without reduced motion. It fails on any of:
- a console or page error;
- horizontal overflow;
- a hero that draws nothing;
- a player without controls;
- anything playing under reduced motion.

## Portfolio card

Each published project can add an entry to `site/portfolio/portfolio.json` in the same shape as the main entry: a
title, one sentence, three facts each with its `source` in `site/data`, a still and a short silent animation recorded
from the page's own hero, and the canonical URL.
