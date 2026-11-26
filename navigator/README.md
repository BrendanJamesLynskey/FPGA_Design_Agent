# The navigator (brief 103)

A local web front end over the agent's command line. It reads the managed-project manifest, the run records and the committed results,
draws them, and shows the CLI command a click corresponds to. It contains no design logic: everything it shows can be produced from the
command line. Stage 1 was read-only. **Stage 2 (brief 103S2)** can also start and stop an agent run with the CLI's own guards, show any run's live
progress, and run locked, read-only board actions; each of these needs a click, a confirmation and the session token.

```
python -m navigator [--port 8765] [--runs DIR] [--captures DIR ...] [--handoff DIR]
```

It prints one address, `http://127.0.0.1:<port>/?t=<token>`. Open that: the token moves into a cookie and the address bar is clean. The token is new
each time the service starts.

## What keeps it private

| Rule | Where it is enforced |
|---|---|
| Binds to 127.0.0.1 only; any other host is refused at start-up | `server.make_server` |
| The `Host` header must be the loopback address and the port in use (DNS rebinding) | `App.host_ok` |
| Every request needs the session token (HttpOnly, SameSite=Strict cookie) | `App.token_ok` |
| Every request calls the access gate (`agent.access.require`), so a revoked or expired key stops it answering; the entry point calls `require_or_exit` | `server._common`, `__main__` |
| An action (POST) needs the token in the header (the cookie alone is refused), `Content-Type: application/json`, the service's own `Origin`, and one of the fixed routes: the three health actions, `/api/run/start`, `/api/run/stop`, `/api/board/run`, (Stage 3) `/api/run/ask`, `/api/run/request`, `/api/run/answer`, and (brief 222) `/api/permissions/save`; each of the last seven also needs a confirmation field the page sends (and a key the route does not take is refused) | `do_POST`, `App.post` |
| No external font, script or image: the Content-Security-Policy names no host, and the shipped files contain no URL | `server.CSP_APP`, tests |
| No endpoint returns a key, token or prompt text: readers copy named fields only, and every response passes `redact.scrub`; a run's prompts appear as names and SHA-256 hashes | `sources.py`, `redact.py` |
| The request never names a file to open: capture ids and record paths are looked up in lists the service built, and records are limited to `results/`, a design's `project.yaml` and `latency_stages.yaml` | `measure.resolve`, `sources.read_record` |

It is not a defence against someone who can edit the code or read your terminal (the token is printed there).

## The pages

| Page | Shows | Comes from |
|---|---|---|
| Project | the hierarchy as a tree; ownership (owned, frozen, excluded), level and a trust meter per component; a drawer with interface contract, provenance and evidence files; a scope picker that shows what the scope allows and the exact `python -m agent resume ... --scope ...` command to copy | `designs/*/project.yaml`; trust is `agent.core.managed.trust` (computed from evidence), the scope is `managed.resolve_request` (the agent's own resolver) |
| Timing | the 97 latency chain stage by stage (clocks and ns, domain, cumulative, post-route slack where recorded, whether the stages reconcile with the bench); every post-route build's WNS, WHS, resources, power, gates and Vivado version | `designs/*/latency_stages.yaml` through `flow/latency/model.latency_path`; `results/*/builds/*/digest.json` and `run.json` |
| Runs | run history with stop reason, cost (provider-reported, or the plan's estimate, labelled), wall time, scope; a drawer with roles, the resolver's model calls, Claude Code calls, and prompt names and hashes | `runs/*/summary.json`, `model_calls.jsonl`, `claude_code_calls.jsonl`, `role_usage.jsonl`, `claude_code/*.prompt.json` (hash fields only) |
| Measurements | the 96D eye viewer (eye, bathtub, 3-D bathtub with two slice sliders, compare with a difference map) for one or two captures; board sessions (CDR and block-lock time, E and L histograms); the frequency-offset sweeps (board and simulated); the rate-match buffer latency by phase; supply and temperature at the start and end of each record | `fda-capture-eye/1` files found under `results/` (and `--captures`), `results/*/hw/*/*/stage3.json`, `ppm_session.json`, `ppm_sim_*.json`, `rm_latency_sim.json` |
| Health | live checks (see below) | local files, version queries, `/proc`, `/sys/bus/usb` |
| Live | every run directory (started from this page or the command line): stage, visit, the stage track, provider-reported cost against the run's budget and the plan's estimate, gate results, the tail of the audit log; refreshes every 5 s | `runs/<id>/config.json`, `role_usage.jsonl`, `trace.jsonl`, `snapshots.json`, `<design>/build/audit.jsonl`, `summary.json` (`progress.py`) |
| Start | start an agent run: a course task (`benchmark/course/tasks`) or a managed project change request, with arm, board, harness, model (from the resolved table), effort and a budget cap; shows the guards | `runctl.py` |
| Permissions | (brief 222) what a run may do without asking: a mode picker (Plan, Ask, Auto within limits, Full auto), the table of the twelve gated actions with each mode's value and a per-action override, the fixed list of what is never allowed, and the command-line flags the settings amount to; saved per project | `agent/core/permissions.py`, `permissions.yaml` in the config folder |
| Examples | (brief 195) a few development tasks with reference runs; re-run one with the pinned setup and compare it: what should match (tool results for the same RTL), what varies with the model (RTL, loops, tokens, cost, time), and the hidden-test verdict | `agent/repro/examples.yaml`, `results/195_repro_examples`, a run's `example_result.json` |
| Board | locked, read-only actions on a board in `boards.yaml`: list JTAG targets, read the build ID and FEATURES, SYSMON, link status | `boardops.py` |
| Models | brief 108's resolved model table, which layer set each value, and whether each endpoint's key is present | `python -m agent models show` |

Every number names its source file and date (a click shows the record). The Measurements page never measures: a scan is the gated board tool
(`python -m flow.eyescan run`, through `_handoff/board.lock`), and there is no button for it. **The eye captures in the repository are synthetic**
(`flow/eyescan/fake.py`); every view labels them so. The board's eye is measured (`results/b96d/hw/20261120_105134`, and the taller scan `20261120_221528`); those records are not synthetic. Drawing is `flow/eyescan/page.py`'s code, served as it
is (one implementation); this brief added the difference map to its Compare tab and the two slice sliders to its 3-D tab.

## Health: free checks and actions

Free checks run when the panel is opened (cached for a minute) and each shows its status, the time and how it was checked. A check that spends
tokens or calls GitHub is an **action**: it runs only on a click.

| Group | Free (automatic) | Action (a click) |
|---|---|---|
| LLM availability | `claude --version`, `claude auth status` (signed-in state, method, provider, expiry only), the model table and whether each key is present | `agent models check --probe` (one minimal call per endpoint, spends tokens) |
| Weekly usage | the last line of `_handoff/usage_log.txt` against the owner's stop line (90 % until the 23 Nov reset; `FDA_USAGE_STOP_PCT` changes it), and how old it is | `_handoff/usage_check.sh` (0 tokens) |
| Tools | Vivado (install path, pinned against installed, licence tier from the committed probe; never started), Yosys, eqy, SymbiYosys, Verilator, Icarus, cocotb, RapidWright and Java (present or not) | |
| Resources | the two heavy-slot locks (holder, age, stale), memory and load against the admission rule, disk | |
| Boards | `boards.yaml` (serials cut to 4 characters), the board lock, USB cables by vendor id from sysfs | (none here: the hardware reads are on the Board page, behind `board.lock` and a heavy slot) |
| Repository | the access gate armed, the knowledge-bank pin against the local checkout, the prompts pin | CI status of `main` (one GitHub API call) |

## Stage 2: starting a run

`Start` builds one of two agent command lines from validated fields and starts it with `subprocess.Popen` (no shell) in its own session:

```
python -m agent run benchmark/course/tasks/<task>/spec.md --board B --harness H --cc-model M --cc-effort E --harness-arm A --max-usd N
python -m agent resume designs/<managed project> "<request>" [--scope c1,c2] --harness H ... --max-usd N
```

The browser sends names, never a command: the task, board, project and components are looked up in lists the service builds (so nothing outside
`benchmark/course/tasks` can be named), the model must be one the resolved table offers, `fable`, `opus` and `anthropic/` are refused, and the
owner's `--allow-fable` flag is never passed. The change request cannot start with `-`. The budget is a number above 0 and at most $10.

Guards, in order; each refuses with its reason and starts nothing:

| Guard | How |
|---|---|
| access gate | the server calls it on every request, and `runctl` calls it again before a start |
| one navigator run at a time | the registry; the PC allows two heavy jobs in all, shared with other sessions |
| usage | `_handoff/usage_check.sh` is run, the new line must be at most 15 min old, and a weekly (all models) figure at or above the stop (90 % until the 23 Nov reset) refuses; a failed or unreadable check refuses (fail closed) |
| heavy slot | `_handoff/take_heavy_slot.sh "103S2: agent run ..., expected end hh:mm"` (the script holds the admission rules); refused if none is free |

The slot is released when the process ends, on every path, only if the lock file still holds the exact text written (another session's lock is never
touched). `Stop` signals only the process group of a run this navigator started: the registry keeps pid, start time (`/proc/<pid>/stat`) and group, all
three are checked again before SIGTERM, and SIGKILL follows after 20 s. The registry (`~/.local/state/fpga_design_agent/navigator/navigator_runs.json`)
lets a restarted navigator release the slot of a run that has gone. A run's output goes to `runs/_navigator/<id>.log`. Live progress works for any run
directory, so a run started from the command line shows too.

## Stage 2: board actions

Four read-only actions, and "all four in one session", for a board in `~/.config/fpga_design_agent/boards.yaml`:

| Action | Reads | Needs |
|---|---|---|
| List JTAG targets | the targets and devices `hw_server` sees (cable serials cut to 4 characters; the board's own cable is marked) | any board |
| Read build ID and FEATURES | ID, BUILD and FEATURES over the design's USER4 register bus, decoded (FEATURES bit names from the register map) | a register profile (the KR260's `b96_kr260_10g`) |
| Read SYSMON | die temperature, VCCINT, VCCAUX, VCCBRAM, each against the recommended operating conditions with the verdict "inside ROC" or "outside ROC" and the source of the limits | any board (limits: DS925 for the KR260, DS181 for Artix-7; otherwise shown, not judged) |
| Read link status | GT_STAT bits (TX_DONE, RX_DONE, PCS BLOCK_LOCK, MOD_ABS, RX_LOS, TX_FAULT ...) | the KR260 profile |

Each action: refuses an unknown board, action, serial or device; takes `_handoff/board.lock` (exclusive create, `103S2:` text) and refuses, naming the
holder, if it is held; takes a heavy slot (it starts `hw_server` and Vivado's hardware manager); runs; releases the slot and then the lock on every path
(success, refusal, error, timeout), only if each file still holds the text written.

**It never programs, writes a register, sets a hardware property, or touches the laser, the flash or the eFUSE.** How that is enforced, and tested
(`navigator/tests/test_103s2_navigator.py`):
- the Tcl is built from fixed templates; `boardops.check_tcl` runs on every script before it is executed and refuses any hardware command outside a list of
  14 read or open/close commands, any `set_property` (so not even the cable clock), anything that programs, writes, boots, erases, sources a file or
  runs a command, any procedure but the two read-only scan procedures, and any register scan word that is not a read of ID, BUILD, FEATURES or GT_STAT
  (read bit set, write bit clear, data zero);
- the register read is a read-only copy of `b58a_rd`; `jtag_regs.tcl`, whose write procedure exists, is never sourced;
- a syntax-tree test of every navigator module: no import of the programming flow, the bench drivers, the debug core or the eye-scan board driver, and
  `boardops` uses only `HwServer`, `preflight`, `vivado_cmd` and `HwError` from `flow.hw`;
- the real transport (hw_server and `vivado -mode batch`, each in its own process group, memory-capped by `flow.hw`) is replaced by a fake in every test.

## Examples: re-run one and see what reproduces (brief 195)

Owner, 2026-11-23: the navigator should offer a few examples a user can re-run to see for themselves that the results reproduce, within the limits of the chosen model's
reproducibility. The command line comes first; the **Examples** page calls the same code (`agent/repro`). The full description, the pinned setup, the measured results and what a user
could guess wrong are in [docs/reproducible_examples.md](../docs/reproducible_examples.md).

| Feature | CLI | Page | Reads | Writes |
|---|---|---|---|---|
| The examples and their reference runs | `python -m agent example list` | Examples: one panel per example (what it covers, reference runs, wall time and cost as min / median / max) | `agent/repro/examples.yaml`, `results/195_repro_examples/<example>/ref_<n>.json` | nothing |
| Re-run with the pinned setup | `python -m agent example run <name> [--max-usd N]` | Examples: "Re-run with the pinned setup" (a confirmation first) | the pins, the installed tools | a run directory, `example_result.json` in it |
| Compare a finished run | `python -m agent example compare <run_dir>` | Examples: "Compare a finished run" | `example_result.json`, the reference records | nothing |
| Tools repeat on the same RTL | `python -m agent example tools <name> --ref N` | (command line) | a stored reference RTL | nothing outside a scratch build |

The page adds **no new POST route**: a re-run goes through `/api/run/start` with `kind: "example"` and the Stage 2 guards (confirmation, access gate, usage stop, one run at a time,
heavy slot). The browser sends the example's name and, optionally, a lower cost cap; the model, effort, harness, arm, verification level and stop stage are the pins and cannot be
changed from the page (that is the point of the example). The child command (`python -m agent example run <name> --no-slot`) runs the **pre-flight** again and refuses, naming the
check, when a pin does not hold: the pinned copy of the Claude Code CLI (version and SHA-256), Vivado 2026.1, the knowledge-bank checkout at the commit the prompt pin names, and a
model that is not Fable or Opus. The two read routes are `GET /api/examples` and `GET /api/examples/compare?id=<run id>` (a run from the list the service built, never a path).

## Tests and screenshots

`python -m pytest navigator/tests` (fakes for the runner, the spawner and the board transport: the tests show which commands a page load, a start or a board action would run, and that no process or board is touched).
`NODE_PATH=<node_modules> node navigator/shoot.js <url with token> <dir>` takes the screenshots of `results/103_navigator/` and checks for page
errors, horizontal overflow at 390 px and any request outside the service. Results and limits: [results/103_navigator](../results/103_navigator/README.md).
`NODE_PATH=<node_modules> node navigator/shoot_stage2.js <url> <dir> <handoff dir>` does the same for Start, Live and Board against `python -m navigator.tests.demo_stage2` (fake spawner and board transport); see results/103s2_navigator.

## Stage 3: updates, a live console, questions and mid-run requests (brief 182)

Owner, 2026-11-22: the navigator should "offer regular updates on what's happening, and the ability to ask questions, and inject mid-session
requests". Every feature is a CLI command first; the page calls the same code. Nothing here moves the Stage 1 and Stage 2 privacy rules: the new
routes are in the table below and follow every row of "What keeps it private".

| Feature | CLI | Page | Reads | Writes |
|---|---|---|---|---|
| Plain-words status | `python -m agent status <run_dir> [--follow]` | Live: "What is happening" | the run's own records (`trace.jsonl`, `role_usage.jsonl`, `snapshots.json`, `audit.jsonl`, `requests.jsonl`, `qa.jsonl`, `summary.json`) | nothing |
| Live console | `python -m agent status <run_dir> --console [--step ID]` | Live: closed drawer "Console" | `<run_dir>/console/*.log` and `claude_code/*.jsonl`, named by the trace's `console` events | nothing |
| Ask a question | `python -m agent ask <run_dir> "<question>"` | Live: "Ask about this run" | the same redacted records as the status | `<run_dir>/qa.jsonl` only |
| Mid-run request | `python -m agent request <run_dir> --control pause\|stop-after N\|abort` or `--design "<text>"` | Live: "Ask the agent to change something" | `requests.jsonl`, the run's state | `<run_dir>/requests.jsonl`, `build/who_did_what.json`, the run's summary |

### Regular updates (no model call)

The summary is derived by code from the run's records: what the run has done (stages finished), what it is doing (stage, visit, role, the step
running now and for how long, for example "Vivado implementation, 4 min"), what is next, what is blocked or waiting (a heavy-slot wait, a review
interrupt, an interview question, a paused run, a queued request) and the cost against the cap. The page refreshes it every 5 s while the Live page is open; the
**text** is rebuilt when a stage ends and at least every 5 minutes (`FDA_STATUS_MIN`, default 5) so it does not flicker. No model is called. The agent
adds the events the summary needs as `kind: "event"` rows in its existing `trace.jsonl` (stage start and end, a build step with its elapsed time, a slot wait,
a console pointer, a request outcome); there is no second log.

### Live console (optional, closed by default)

A drawer that shows the output of whatever the run is doing now: the model's streamed output (assistant text and tool calls with their arguments
summarised), Vivado's log, the simulator's or formal tool's output, test runs. A label says which tool, since when and the source file. The agent now
writes each external tool's output to `<run_dir>/console/<n>_<tool>.log` as the tool runs (the Claude Code stream goes to `console/<n>_<role>.log` the same way),
and says so in the trace with a `console` event. The browser asks for a **step id from a list the service built**, never a path; reads are incremental
(a byte offset), at most 256 KB per answer (the last 256 KB when the first read is of a large file), and the page polls only while the drawer is open.
Every chunk passes `redact.scrub`. **Prompts stay names and hashes**: the model's prompt text is never in a console file and never shown; for a held-out or scored
run the console shows tool names and progress lines only, no model text.

### Ask a question

A separate, read-only model call answers a question about a run. It uses the model table's `review` purpose (a Claude Code Sonnet call by default; never
Fable or Opus, never `anthropic/` through OpenRouter), is given only that run's records as the status reader returns them (redacted, named, each with a record id
such as `[R3] role_usage.jsonl`), has no tools and cannot write to the design or alter the run. The answer lists the record ids it was given and the ones it cited. Each
exchange is appended to `<run_dir>/qa.jsonl` with its cost; the cost is the plan's estimate (Claude Code on the subscription) or the provider-reported figure, and
counts against a **separate cap** of $0.50 and 20 questions per run (`FDA_QA_USD`, `FDA_QA_MAX`), apart from the run's own budget.

### Mid-run requests

Two kinds. **Control**: `pause` (stop at the next safe point and wait; resume with `python -m agent resume <run_id> --reply '{"resume": true}'`), `stop-after N` (end the run when stage N has passed) and
`abort` (end the run at the next safe point; the Stage 2 Stop button still signals the process at once). **Design**: free text, for example "use block RAM for the FIFO". A request is queued
in `<run_dir>/requests.jsonl` (append-only: one row per event) and applied **only at a safe point: a stage boundary, which includes the moment after a review interrupt is answered, never in the middle of a tool call or a model turn**.
At a safe point the agent acknowledges it (`accepted`, saying when and which stage it affects) and then records `done` or `declined` with a reason; the page shows the history. A design
request goes to the next stage's writer as the owner's note; if its words name an earlier stage (the pickup classifier, `agent/graph/pickup.py`) the run is **rewound** to that stage through the
snapshot rewind (the files return to that stage's snapshot) and the note goes there. Each request counts as a user intervention in `build/who_did_what.json` and in the run's `summary.json`.
If the run reaches a question of its own (the interview, with `--interview on`) it pauses; the page shows the question with its default and lets the user answer, which resumes the run
with the Stage 2 guards (usage check, heavy slot).

### Evaluation guard

A run is **scored** when its `config.json` names a hidden spec (the benchmark runners do) or the run directory holds a `SCORED` marker file. Ask and design requests are **refused** for a
scored run (a model answer or a design note would make the result not comparable); control requests stay allowed; the console shows tool names and progress lines only.

### New POST routes

| Route | Body | Confirmation | Does |
|---|---|---|---|
| `POST /api/run/ask` | `{id, question, confirm: "ask"}` | `confirm` must be `"ask"` | one read-only model call, appended to `qa.jsonl` |
| `POST /api/run/request` | `{id, kind: "control"\|"design", action?, stage?, text?, confirm: "request"}` | `confirm` must be `"request"` (the page asks the user first) | queues one request |
| `POST /api/run/answer` | `{id, answer, confirm: "answer"}` | `confirm` must be `"answer"` | resumes a run paused on its own question, with the Stage 2 guards |

Each needs the token in the header, the service's own `Origin`, `Content-Type: application/json`, the access gate, and refuses any key it does not know. The body never carries a file name, a path or a
command-line flag: `id` is looked up in the list of run directories the service built, `action` and `kind` come from fixed lists, `stage` is an integer, the text (at most 500 characters) is
stored as data and never reaches a command line, and text that starts with `-` is refused. The three read-only GET routes are `/api/live/summary`, `/api/console/steps`+`/api/console/read` and `/api/live/requests`.

### What a user could guess wrong

- **A request is not instant.** It waits for the next safe point, which can be minutes away (a Vivado step must finish first). The page says "queued" until then.
- **A pause stops the process.** The run is resumed from its checkpoint with `python -m agent resume <run_id> --reply '{"resume": true}'` (the reply is what lets it past the pause); the page does not hold it open.
- **A design request can rewind.** If it names an earlier stage, work after that stage's snapshot is discarded (it stays in the git history of the snapshots).
- **Stop-after N is "after the gate passes".** If stage N fails and loops, the run continues until N passes.
- **The answer to a question is a model's reading of the records, not a record.** It can be wrong; the cited record ids say where to check. It cannot see prompts, source files or logs, only the status records.
- **The status text is code, not a model.** "What is next" is the stage machine's next stage on a pass; a failure may send the run back.
- **The console can be empty** for a step whose tool writes nothing until it ends, and Vivado's own log appears as it is written to the tool's captured output.
- **Costs differ.** The run's cost is the provider-reported figure; Claude Code on the subscription reports none, so the plan estimate is shown, labelled.
- **Phone access is not provided**: the page stays on 127.0.0.1 (options for the owner are in the report).

### Tests and screenshots (Stage 3)

`python -m pytest navigator/tests/test_182_navigator_s3.py agent/tests/test_182_requests.py agent/tests/test_182_console.py` (a scripted model and fake runner stand in for the agent's tools; a fake stands in for the
question's model call). `NODE_PATH=<node_modules> node navigator/shoot_stage3.js <url with token> <dir> <run id>` shoots the Live page at 1280 and 390 px with the console drawer shut and then open, and
fails if the drawer polled while shut. Results: [results/182_navigator_s3](../results/182_navigator_s3/README.md).


## Permission modes (brief 222)

The **Permissions** page sets what a run may do without asking; the full description of the modes, the twelve actions and what is never allowed is in
[docs/agent.md](../docs/agent.md#permission-modes-brief-222). What the Navigator adds:

- **Saved per project** in `permissions.yaml` in the config folder (`~/.config/fpga_design_agent/`; the Navigator always uses this file, so `FDA_PERMISSIONS_FILE`, which moves the command line's file, makes the two differ): `mode`, `overrides` and `ask_above_usd`, for
  every project (the top level) or one project (under `projects:`; a course task or a managed project, by name). `python -m agent` reads the same file, and the command line
  (`--permissions`, `--allow`, `--deny`, `--ask`, `--ask-above-usd`) wins. With nothing saved the Navigator uses **Ask**; the command line alone uses Auto (what a run was before this brief).
- **A run started from the Start page passes its mode on the command line** (`--permissions <mode>`, one `--allow`, `--deny` or `--ask` per override that differs from the mode, `--ask-above-usd`),
  so the run record says "command line". The Start page's picker chooses another mode for that run only. A run started here stops after stage 8, so it never reaches the board whatever the mode.
- **A permission question appears on the Live page**, in the same place as the agent's own questions: the actions it needs, in plain words, with *Allow and resume* and *Deny*. Allow resumes the
  run with the usual guards (usage check, heavy slot); Deny ends it with the reason in its record. The answer is recorded with the time.
- **The Board page's read-only actions follow the default settings' `read_board`**: Plan refuses them; Ask, Auto and Full still need the confirmation click the page already asks for (that click is the ask).
- **One more POST route**, `/api/permissions/save` (`{project, mode, overrides, ask_above_usd, confirm: "save"}`): same rules as every action (token in the header, own Origin, JSON, access gate,
  a key it does not take is refused, the project looked up in the list the service built, only values from the fixed lists). Saving changes the next run, not one already going.

### What a user could guess wrong (permissions)

- **The saved settings are not the settings of a running run.** A run keeps the mode it started with (it is in its `permissions.json`); resume it with `--permissions` to change that.
- **Full auto from the Start page still does not touch the board** (stage 8 is the limit there). From the command line it does.
- **A deny override can block a stage the run needs**: the run stops there, with the reason, and nothing is spent on that stage. Remove the override and resume.
- **Save for "every project" does not change a project that has its own entry.** The project's entry wins.

### Tests and screenshots (brief 222)

`python -m pytest navigator/tests/test_222_navigator.py agent/tests/test_222_permission_modes.py`. `python3 -m navigator.tests.demo_222 --port 8795 --workdir <tmp>` serves the page with fakes (and a temporary
config folder, so the owner's settings are untouched); `NODE_PATH=<node_modules> node navigator/shoot_222.js <url with token> <dir> <run id>` shoots the Permissions, Start and Live pages at 1280 and 390 px
and fails on a page error, an overflow at 390 px or a request to another host. Screenshots: [docs/img/222_permissions_auto_with_deny_wide.png](../docs/img/222_permissions_auto_with_deny_wide.png),
[docs/img/222_live_permission_question_wide.png](../docs/img/222_live_permission_question_wide.png).

## Stage map (brief 238)

The **Live** page draws, above the plain-words status, a map of the stages of the selected run and moves it as the run's files change. Results and recordings: [results/238_navigator_animation](../results/238_navigator_animation/README.md).

- **Drawn from the code.** `navigator/stagemap.py` takes the stages, their visit limits and the allowed route-backs from `agent.graph.stages.MACHINE`, so a stage added there appears by itself. The route is `GET /api/live/map?id=<run>`; `static/stagemap.js` draws it (inline SVG and CSS, no library, no inline style).
- **One list of recorded events.** Each event is a row some run file holds, with the state of every stage after it. Kinds: `enter` (`stage_start`), `role` (a `role_usage.jsonl` row), `gate` (an audit-log `gates` call, or a ledger row), `leave` (`stage_end`), `step` (`build_step`, `console`, `console_end`), `wait` (`slot_wait`, `permission_stop`, a pause request, `pending.json`), `resume` (`permission_granted`, a pause request done), `request` (the other request rows) and `end` (`summary.json`). Two modes, named in the answer: `trace` (the run has `trace.jsonl`) and `role_usage` (a folder without it: the order of the `role_usage.jsonl` rows is the order of the visits, failing gates come from `routing_events.jsonl`, and whether a visit passed is read from where the run went next; these rows carry no times).
- **What moves.** The current stage has a moving dash on its border (stops when the run is idle or finished); a token travels along the edge on a stage change (about 600 ms); a route back travels a separate dashed arc in the warning colour, labelled with the failing gate ("lint: back to stage 1"); a gate result flashes its stage; a running tool shows a small spinner; a wait (Vivado slot, a permission, a question, a review, a pause) is a still badge with its reason.
- **Truth rule.** Nothing is interpolated: no percentage, no invented step. A run with no write for longer than `ACTIVE_S` (180 s) stops moving and says "No activity for N min"; a finished run freezes with its stop reason. `progress.py` is unchanged and nothing is written.
- **Replay** (finished runs): steps through the recorded events at an even pace with a speed control (0.5x to 4x), with the same drawing.
- **Access.** `prefers-reduced-motion`: no token, no dash, no spinner turn, no flash (state changes only). The current stage is announced in an `aria-live` region. Every state also has an icon and a word (pass, fail, working, waiting, not reached). At 640 px and below the map is a vertical list with the same states.

### What a user could guess wrong (stage map)

- **The role shown is the last role that reported in the visit**, not one that is mid-call: `role_usage.jsonl` rows are written when a call ends.
- **In a folder without `trace.jsonl`, a passed or failed stage is inferred from where the run went next**, and a retry because a reviewer asked for changes looks like a gate failure; a route back caused by a design request looks like one caused by a gate. Passing gates are not events there (the ledger holds failing gates only).
- **An idle run with no summary** may have crashed, finished badly or be inside one long step that writes no log; the map says only how long nothing was written.
- **A Vivado slot wait** is shown only while its row is under 5 minutes old and the build step is open.

Tests: `python -m pytest navigator/tests/test_238_stagemap.py` (recorded 213 run folders trimmed in `navigator/tests/fixtures_238/`, and a synthetic trace-mode run). Evidence: `python3 -m navigator.tests.demo_238 --port 8794 --workdir <tmp>` then `NODE_PATH=<node_modules> node navigator/shoot_238.js <url with token> <dir>` (screenshots, a WebM of a replay, a reduced-motion check; fails on a page error, an overflow at 390 px or a request to another host).
