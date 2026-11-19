# The navigator (brief 103)

A local web front end over the agent's command line. It reads the managed-project manifest, the run records and the committed results,
draws them, and shows the CLI command a click corresponds to. It contains no design logic: everything it shows can be produced from the
command line, and stage 1 starts no run.

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
| An action (POST) needs the token, `Content-Type: application/json`, the service's own `Origin`, and one of four fixed action names | `do_POST`, `health.Health.ACTIONS` |
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
| Models | brief 108's resolved model table, which layer set each value, and whether each endpoint's key is present | `python -m agent models show` |

Every number names its source file and date (a click shows the record). The Measurements page never measures: a scan is the gated board tool
(`python -m flow.eyescan run`, through `_handoff/board.lock`), and there is no button for it. **The eye captures in the repository are synthetic**
(`flow/eyescan/fake.py`); every view labels them so, and the board's eye is not measured yet. Drawing is `flow/eyescan/page.py`'s code, served as it
is (one implementation); this brief added the difference map to its Compare tab and the two slice sliders to its 3-D tab.

## Health: free checks and actions

Free checks run when the panel is opened (cached for a minute) and each shows its status, the time and how it was checked. A check that spends
tokens, calls GitHub or touches the hardware server is an **action**: it runs only on a click.

| Group | Free (automatic) | Action (a click) |
|---|---|---|
| LLM availability | `claude --version`, `claude auth status` (signed-in state, method, provider, expiry only), the model table and whether each key is present | `agent models check --probe` (one minimal call per endpoint, spends tokens) |
| Weekly usage | the last line of `_handoff/usage_log.txt` against the 88% stop line, and how old it is | `_handoff/usage_check.sh` (0 tokens) |
| Tools | Vivado (install path, pinned against installed, licence tier from the committed probe; never started), Yosys, eqy, SymbiYosys, Verilator, Icarus, cocotb, RapidWright and Java (present or not) | |
| Resources | the two heavy-slot locks (holder, age, stale), memory and load against the admission rule, disk | |
| Boards | `boards.yaml` (serials cut to 4 characters), the board lock, USB cables by vendor id from sysfs | a hardware-server listing (`flow/hw_list.tcl`, read-only; refused while the board lock is held) |
| Repository | the access gate armed, the knowledge-bank pin against the local checkout, the prompts pin | CI status of `main` (one GitHub API call) |

## Tests and screenshots

`python -m pytest navigator/tests` (the runner is a fake that records every command, so the tests show which commands a page load starts).
`NODE_PATH=<node_modules> node navigator/shoot.js <url with token> <dir>` takes the screenshots of `results/103_navigator/` and checks for page
errors, horizontal overflow at 390 px and any request outside the service. Results and limits: [results/103_navigator](../results/103_navigator/README.md).
