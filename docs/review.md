# Design review mode (brief 84)

```
python -m agent review <design-dir> [--out DIR] [--intent FILE] [--improvements FILE] [--no-judge] [--claude-bin PATH]
```

Given a design the agent did not write (a directory with RTL, tests, constraints and docs, and an optional statement of intent
`spec.md` or `INTENT.md`), it writes the review a senior FPGA engineer would. **It never edits the reviewed design**: it works on a
copy under `runs/review/`, hashes the reviewed tree before and after, and writes only to `--out` (default `runs/review_out/<name>`).

| Output | What |
|---|---|
| `review.json` | the record: understanding, findings, dismissed check findings, questions, verification gap, checks that ran, the reviewer call's usage |
| `REVIEW.md` | for an engineer: understanding, block diagram, findings by severity, verification gap, questions, what was and was not checked |
| `REVIEW_AGENT.md` | the same findings, one line each, for the agent |
| `handover/` | `handover.yaml`, `README.md`, `AGENT.md`, marked "produced by review", when the design has no handover |
| `block_diagram.svg` | the top module and its instances, from the source hierarchy |

**Finding** (`flow/review/schema.py`): `id`, `title`, `severity` (critical, major, minor, info), `category` (a closed set), `location`
(file, line, end line, object), `evidence`, `rule`, `fix`, `confidence` (high, medium, low), `source` (`check:<name>`, `judge`, `both`).

**Parts.** The check suite (brief 71) runs at RTL scope: Verilator lint, the design-standards check, the reset elaboration (Yosys with
slang), the AXI rules. Facts made by code (modules, ports, clocks, hierarchy). One reviewer call (`claude -p`, no tools, the files in the
prompt with line numbers) reads the design and the check findings and writes the understanding, its own findings, which check
findings it dismisses, questions and the verification gap. `--no-judge` is the check suite alone.

**Improvement requests** (`--improvements`, one plain-English request per line): each is restated as a measurable goal with an
acceptance test (or one question is asked), assessed against the design, and ordered by code (dependencies, then findings to fix first, then
cost); each item gets the stage at which `python -m agent resume` would enter. A plan only: nothing is carried out.

**What a user could guess wrong.** No synthesis runs, so the CDC report, methodology, DRC and timing checks do not run: clock-domain crossings
are found by the reviewer's reading only. No simulation, coverage or mutation run is made: the verification gap is reasoning from the test
files. The hierarchy is read from source text, not an elaborated netlist. Findings with `confidence: low` may be wrong; a clean review is not
a proof. The reviewer is a language model: two runs on one design differ. Measured results: `results/84_review/README.md`.
