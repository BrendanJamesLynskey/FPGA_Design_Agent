# The agent documents its own work: three recorded runs (brief 68 part C)

Three agent runs recorded before brief 68, documented after the fact by the agent's own DOC step: code drafted each
design's `handover.yaml` from the run's records, the Designer role (`claude-sonnet-5-5` through Claude Code on the Max
plan, no OpenRouter spend) wrote the prose, and the flow rendered `README.md` and `AGENT.md` and ran the DOC gate. No
stage of any run was re-run and no new design work was done: these are the runs as they ended. How the step works:
[docs/agent.md](../../docs/agent.md) and [docs/documentation_standard.md](../../docs/documentation_standard.md#agent-produced-designs).

| Run | Design | How the run ended | Agent README | DOC gate |
|---|---|---|---|---|
| [20261107-005621-8deb](20261107-005621-8deb/) | `c14_int8_dot_requant` (course task) | stage 2 (RTL and verification) failed its gates; verification reached V2 of V3 | [README](20261107-005621-8deb/c14_int8_dot_requant/README.md), [AGENT](20261107-005621-8deb/c14_int8_dot_requant/AGENT.md) | passed on the first Designer pass ([doc.json](20261107-005621-8deb/doc.json)) |
| [20261102-135505-a8f2](20261102-135505-a8f2/) | `t1_dimmer_counter` | stages 0 to 8 passed; stage 9 (configuration and debug) failed because the debug build with the ILA left only an error stub | [README](20261102-135505-a8f2/t1_dimmer_counter/README.md), [AGENT](20261102-135505-a8f2/t1_dimmer_counter/AGENT.md) | passed on the second Designer pass ([doc.json](20261102-135505-a8f2/doc.json)) |
| [20261102-114228-5a32](20261102-114228-5a32/) | `t1_dimmer_counter` | stage 9 failed (no debug-build record) and the run stopped at the visit limit; the old summary counted the refused final entry into stage 6 (timing closure) as a failure, which the build records contradict (see the handover) | [README](20261102-114228-5a32/t1_dimmer_counter/README.md), [AGENT](20261102-114228-5a32/t1_dimmer_counter/AGENT.md) | passed on the second Designer pass ([doc.json](20261102-114228-5a32/doc.json)) |

All three runs built with a Vivado release earlier than 2026.1, so their READMEs publish no timing, resource or power
number: the build evidence is `partial` and each of those quantities is a known gap. Re-measuring (`python -m agent resume`)
is the first next step in each. The READMEs were regenerated in brief 68F (a second round, after an independent re-review): the
code now puts each failing gate's detail beside the run's own build records, names the V-stage reached, and fills the run's
provenance (model, loops, turns, wall time, tokens, cost), coverage, mutation sample and ILA probes from the records.

## Records

Each run folder holds a copy of what the run left, enough for its handover's claims:

- `summary.json`: the run summary the harness wrote (stages visited, the gate result of each stage, the stop reason,
  the interview, provider-reported cost); copied unchanged.
- `config.json`: the run's configuration, with the absolute repository path removed from the file paths.
- `<design>/`: the design directory as the run left it (spec, architecture, RTL, XDC, model, tests, test plan), without
  `build/` outputs except the records below. In `build.yaml` and `verif/testplan.yaml` the run's directory
  `runs/<run>/<design>` is rewritten to this folder's path so the files resolve here; nothing else was edited.
- `<design>/build/`: the flow's records the handover cites: `verif/verif_gates.json`, `verif/mutation.json` (where the
  run made one), `base/gates.json` and `base/run.json` (the Vivado release used), `ila/gates.json`, and the stage
  review pages `review/*.html`.
- `<design>/handover.yaml`, `README.md`, `AGENT.md`, `docs/handover/*.svg`: written by the DOC step.
- `doc.json` (the DOC result), `doc_calls.jsonl` (each pass's prompt size and the Designer's reply, used as the replay
  fixture of `agent/tests/test_68_document_resume.py`) and `doc_claude_code_calls.jsonl` (the Claude Code call's tokens
  and wall time).

## Reproduce

Replaying the recorded reply needs no model and no Vivado; a fresh pass needs the Claude Code CLI and its token.

```bash
# replay the recorded Designer reply (no model call): writes the same handover, README and AGENT
python -m agent document results/68_agent_docs/20261107-005621-8deb --replay results/68_agent_docs/20261107-005621-8deb/doc_calls.jsonl
# a fresh Designer pass (Claude Code on the Max plan)
python -m agent document results/68_agent_docs/<run> --cc-model claude-sonnet-5-5
# the checks CI runs on these designs
python3 flow/doccheck.py --check --strict
```

## Known gaps and limits

- The runs are older than the DOC step: the step was applied afterwards with `python -m agent document`, not at the
  end of the live runs. A live run with `--docs on` (the CLI default) does the same at its end.
- The Designer's prose is checked for numbers, placeholders and length, and the code owns every gate result and
  measurement, but behavioural statements in the prose (for example what an unmapped register read returns) are the
  model's reading of the spec and RTL; nothing checks them against a simulation. An independent reviewer read the three
  READMEs; its findings are in the brief 68 report.
- One DOC step per run (one or two Designer passes), one model (`claude-sonnet-5-5`). How often a first pass fails the gate, and how other models do,
  was not measured.
- `AGENT.md` for these runs is larger than for the hand-written designs (3,488 to 3,793 tokens, characters / 4, against a target of 2,000),
  because the gaps now carry the behaviours the RTL settles, each failing gate's detail and the run's provenance. Stages not
  run and quantities not measured are grouped on one line each in `AGENT.md`, and paths are relative to the design.
