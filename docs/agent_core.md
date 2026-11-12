# The agent core: tools, MCP server, security layer, traces (brief 05a)

The flow's tools as typed Python functions with JSON schemas (`agent/core/`), the same functions as an MCP server
(`agent/mcp_server/`), and a security layer that is enforced in code. Any harness calls the same functions:
the Deep Agents agent in-process (05b), Claude Code or anyone's MCP client over stdio (05c). Nothing in the core
calls a language model.

## Tools

Every tool returns raw tool output plus structured fields, and **never a fix hint** (harness neutrality). Schemas
are `additionalProperties: false`; they are snapshot-tested in `agent/tests/fixtures/tool_schemas.json` and carry
`SCHEMA_VERSION` (`agent/core/registry.py`).

| Tool | What it runs | Arguments |
|---|---|---|
| `read_file`, `write_file`, `list_files` | files inside the design directory (`build/` is read-only) | path, content, offset, max_bytes |
| `lint` | `verilator --lint-only -Wall` over the `build.yaml` sources | none |
| `simulate` | the design's `tests/test_*_rtl.py` (cocotb) under `icarus` or `verilator` | sim |
| `formal` | `flow/formal.sh` (SymbiYosys bounded proof and cover) | none |
| `build` | `flow/run_vivado.sh` (memory-capped) up to `synth`, `place`, `route` or `bitstream`, then the gates | until, variant |
| `gates` | `flow/gates.py` (stage results) or `flow/verif_gates.py` (V-stages), raw | kind, variant |
| `report` | one named report or log from `build/<variant>/` | name, variant, offset, max_bytes |
| `check_constraints` | `design.xdc` against the board: clock only on the board's clock input, no `CLOCK_DEDICATED_ROUTE FALSE`, pins and standards as in the master XDC, XDC command allow-list | none |
| `search_docs`, `load_skill` | the frozen knowledge bank only (`tools/search_docs.py`, `tools/select_skills.py`); text comes back as untrusted data | query, k, sections; `load_skill` also takes `name` (one body, brief 36) |
| `skill_index`, `skill_excerpt` | brief 36, offered to roles only with `--skill-routing router`: ranked skill names and one-line descriptions (BM25 plus embeddings), and one section of one skill ([docs/skill_routing.md](skill_routing.md)) | query, k; name, heading |
| `program` | `flow/program.py`: SRAM only, by the board's cable serial | variant (`target` accepts only `sram`) |
| `bringup` | `flow/bringup.py` | none |
| `stage_note` | append to `BUILD_NOTE.md` and move the session to a stage | stage, text |
| `debug_plan`, `debug_capture`, `debug_query` | brief 50A, not offered to any role yet: a structured capture request to a checked plan; the plan's debug ILA build (optional Vivado run), SRAM programming and a capture with the answer and XADC conditions (hardware rules as `program`, cost 1); questions to a capture ([docs/debug.md](debug.md)) | intent, request; probeset, build; capture, query, other |

Stage-limited builds: `flow/prepare.py` reads `FDA_STOP_AFTER` (`synth`, `place`, `route`, `bitstream`) into
`inputs.tcl`, and `flow/build.tcl` exits cleanly after that stage's reports. The gates mark later stages `ran: false`.

## Security rules and where they are tested

| Rule | Enforced by | Tests |
|---|---|---|
| Files only inside the design directory; `..`, absolute paths, `~` and symlinks resolved first; `build/` and hidden names not writable | `PathJail` | `test_security.py::test_jail_*` |
| The agent never sends Tcl or shell: tools build fixed argv; schemas are strict; `build.yaml` values that reach Tcl (top, part, generics, source and constraint paths) are validated; `design.xdc` commands must be in an allow-list (`FDA-CON-6`) | `validate_args`, `load_build_cfg`, `check_xdc_safety` | `test_tools.py::test_build_refuses_*`, `test_xdc_allow_list_*` |
| Calls out of the simulator in agent-written files (`$system`, `subprocess`, sockets, `eval`...) are refused before a simulation or build | `scan_sources` | `test_source_scan_*` |
| Hardware: the stage must be `configuration-and-debug`; `power_ok` for the recorded power source must pass for every bitstream involved; no serial or device argument exists (the cable serial comes from the local board file); SRAM only, flash and configuration memory refused; a per-session action budget (`program` costs 1, `bringup` 2, `debug_capture` 1; default 6) | `_hw_common`, `HardwarePolicy`, `flow/program.py` | `test_tools.py::test_program_*`, `test_hardware_*`, `test_redteam.py` |
| No key, token or cable serial in model context, trace or audit log | `redact` (applied to every result, argument, audit and trace record) | `test_security.py::test_redaction`, `test_secrets_never_reach_*`, `test_cable_serial_*` |
| Every call and every refusal is logged with time, stage, tool, arguments, result summary and rule | `AuditLog` -> `designs/<name>/build/audit.jsonl` | `test_audit_log_*` |
| Injected instructions in a spec, a knowledge-bank chunk or a UART reply fail safely and are logged | all of the above | `test_redteam.py` (fifteen attack calls per injection, each refused with its rule) |
| The book's deliberate BTNC-as-clock trap is flagged | `check_xdc` `FDA-CON-1`, `FDA-CON-2` | `test_constraints_checker_t1_is_clean_and_the_btnc_trap_is_caught` |

### What this does not do (known gaps)

- **Agent-written tests are host code.** A cocotb or `hw_checks.py` file runs as the owner's user. The static scan and
  a scrubbed environment (no keys; only the variables the tools need) are defence in depth, not a sandbox. Real
  isolation (a network and filesystem namespace) is not available here: unprivileged user namespaces are blocked
  on this PC (`bwrap` fails with "setting up uid map: Permission denied"). Until then, a human reads agent-written
  test files before a hardware run.
- `bringup` writes under `designs/<name>/build/bringup/` (05b; before that it wrote the F0B record folder).
- The file tools can **read** the test shell under the virtual prefix `@shell/` (`@shell/rtl/...`,
  `@shell/PROTOCOL.md`, `@shell/host/protocol.py`; owner decision 2026-11-01); every write there is refused, and
  nothing else in the repo is visible.

## Traces and replay

`agent/core/trace.py`: one JSONL record per event, `v` = 1. A `model` record has harness, model, tokens,
`cost_usd` (the provider-reported number, or the string `"unreported"`; never an estimate; a fake reports 0.0 with
`fake: true`), stage, seconds. A `tool` record has tool, arguments, result (`ok`, `refused`, `rule`, output), stage,
seconds. Strings are redacted before they are written.

`agent/core/replay.py` runs a recorded episode through the real core with a `RecordedRunner` in place of the
tools; `agent/tests/fixtures/t1_episode.json` is the T1 episode (clarify -> ... -> bitstream), recorded on real
tools by `python -m agent.core.smoke --record`. CI fails if the core would run a different command than the one
recorded, or if a deterministic output changes.

## Running it

```bash
python -m agent.mcp_server --design designs/t1_dimmer_counter     # stdio MCP server (mcp==2.3.0, protocol 2026-07-28)
python -m agent.core.smoke --hardware                             # T1 to bitstream, then the board (Vivado, ~15 min)
pip install -e '.[test,agent]' && pytest -q agent/tests
```

**Local tools (05b).** The core finds external tools itself: `~/.config/fpga_design_agent/tools.yaml` (outside the
repo; override with `FDA_TOOLS_FILE`) lists `path` (directories put first on the runs' PATH) and `env` (for example
`VERILATOR_ROOT`). No shell setup is needed. A missing tool fails with an error naming the tool, the file and how to
install it.

```yaml
path: [~/.local/opt/verilator-5048/root/usr/share/verilator/bin]
env: {VERILATOR_ROOT: ~/.local/opt/verilator-5048/root/usr/share/verilator}
```

**Isolation for agent-written test code (05b; owner decision 2026-11-01).** `agent.core.runner.ContainerRunner`
runs `simulate` (the agent's cocotb benches) in a Docker container from `agent/container/Dockerfile`
(`docker build -t fda-sim:2 agent/container`; Ubuntu 24.04, Python 3.12, cocotb 2.0.1, Icarus 12.0, Verilator 5.048 built from the pinned tag in a first stage): `--network none`,
`--cap-drop ALL`, `no-new-privileges`, read-only root, the host uid (not root), memory and pid limits. Mounts: the
design directory read-write; the repo's own `flow/`, `shell/` and `designs/__init__.py` read-only (the benches import
them); tmpfs for the repo `build/` scratch and `/tmp`. No home directory, keys or other designs. Engine: Docker 29
through the docker group. That daemon runs as root (it is not rootless Docker) but the container process is
unprivileged; podman is not installed. `hw_checks.py` runs inside `flow/bringup.py` on the host, because it needs the
UART and Vivado, so it is **not** containerised: any run that would program the board pauses for a review approval
first (see the agent's review gate). **Verilator and mutation in the sandbox (05m).** `fda-sim:2` carries Verilator 5.048 (the host's version; Ubuntu's apt
5.020 is too old for cocotb 2). `available_sims()` offers Verilator when the image has it (probed once per process) or,
with no image, when the host has it; model code never runs on the host while an image exists. `flow/mutate.py --generic`
runs its baseline, every mutant (mutated copies under `<design>/build/mutants`, inside the design mount) and the compile
check through the same `ContainerRunner` (`--sandbox auto|container|host`; the `mutate` tool passes the session's own).
A timed-out container is removed by name (`docker rm -f`). Container limits: `--memory 3g`, `build` tmpfs 1g, `/tmp` 512m (unchanged: the T1 Verilator coverage run peaked at 0.8 GiB and 13 MB of tmpfs).
Rebuild: `docker build -t fda-sim:2 agent/container`, capped with
the `JOBS` build argument (default 2).

Icarus 13, as in the CVDP image, rejects an implicit cast in
`shell/rtl/uart_rx.sv:46`, which 12.0 accepts; this is why the image pins 12.0.

**Results location (05b).** `bringup` runs `flow/bringup.py --results-dir designs/<name>/build/bringup`, so agent runs
never overwrite another milestone's committed results (the F0B record stays as committed).

Reused from the owner's HW Design Space Agent (BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, MIT): the
tracer's redaction approach and JSONL record shape (`agent/trace.py`) and the idea of scripted/replay fakes for
offline tests (`agent/llm.py`). The structured-output LLM wrapper is not used: the core makes no model calls.
