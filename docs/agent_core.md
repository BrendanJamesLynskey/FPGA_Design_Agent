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
| `search_docs`, `load_skill` | the frozen knowledge bank only (`tools/search_docs.py`, `tools/select_skills.py`); text comes back as untrusted data | query, k, sections |
| `program` | `flow/program.py`: SRAM only, by the board's cable serial | variant (`target` accepts only `sram`) |
| `bringup` | `flow/bringup.py` | none |
| `stage_note` | append to `BUILD_NOTE.md` and move the session to a stage | stage, text |

Stage-limited builds: `flow/prepare.py` reads `FDA_STOP_AFTER` (`synth`, `place`, `route`, `bitstream`) into
`inputs.tcl`, and `flow/build.tcl` exits cleanly after that stage's reports. The gates mark later stages `ran: false`.

## Security rules and where they are tested

| Rule | Enforced by | Tests |
|---|---|---|
| Files only inside the design directory; `..`, absolute paths, `~` and symlinks resolved first; `build/` and hidden names not writable | `PathJail` | `test_security.py::test_jail_*` |
| The agent never sends Tcl or shell: tools build fixed argv; schemas are strict; `build.yaml` values that reach Tcl (top, part, generics, source and constraint paths) are validated; `design.xdc` commands must be in an allow-list (`FDA-CON-6`) | `validate_args`, `load_build_cfg`, `check_xdc_safety` | `test_tools.py::test_build_refuses_*`, `test_xdc_allow_list_*` |
| Calls out of the simulator in agent-written files (`$system`, `subprocess`, sockets, `eval`...) are refused before a simulation or build | `scan_sources` | `test_source_scan_*` |
| Hardware: the stage must be `configuration-and-debug`; `power_ok` for the recorded power source must pass for every bitstream involved; no serial or device argument exists (the cable serial comes from the local board file); SRAM only, flash and configuration memory refused; a per-session action budget (`program` costs 1, `bringup` 2; default 6) | `_hw_common`, `HardwarePolicy`, `flow/program.py` | `test_tools.py::test_program_*`, `test_hardware_*`, `test_redteam.py` |
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
- `bringup.py` writes `results/f0b/<design>_bringup.json` outside the design directory (that is flow code, not the
  agent).
- The agent cannot read `shell/rtl` through the file tools (read-only access to the shell RTL is a possible
  addition if designs need it; for now the knowledge bank documents the shell).

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

**Results location (05b).** `bringup` runs `flow/bringup.py --results-dir designs/<name>/build/bringup`, so agent runs
never overwrite another milestone's committed results (`results/f0b/` stays the F0B record).

Reused from the owner's HW Design Space Agent (BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, MIT): the
tracer's redaction approach and JSONL record shape (`agent/trace.py`) and the idea of scripted/replay fakes for
offline tests (`agent/llm.py`). The structured-output LLM wrapper is not used: the core makes no model calls.
