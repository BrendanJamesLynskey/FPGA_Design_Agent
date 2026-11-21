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
| An action (POST) needs the token in the header (the cookie alone is refused), `Content-Type: application/json`, the service's own `Origin`, and one of the fixed routes: the three health actions, `/api/run/start`, `/api/run/stop`, `/api/board/run`; each of the last three also needs a confirmation field the page sends | `do_POST`, `App.post` |
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

## Tests and screenshots

`python -m pytest navigator/tests` (fakes for the runner, the spawner and the board transport: the tests show which commands a page load, a start or a board action would run, and that no process or board is touched).
`NODE_PATH=<node_modules> node navigator/shoot.js <url with token> <dir>` takes the screenshots of `results/103_navigator/` and checks for page
errors, horizontal overflow at 390 px and any request outside the service. Results and limits: [results/103_navigator](../results/103_navigator/README.md).
`NODE_PATH=<node_modules> node navigator/shoot_stage2.js <url> <dir> <handoff dir>` does the same for Start, Live and Board against `python -m navigator.tests.demo_stage2` (fake spawner and board transport); see results/103s2_navigator.
