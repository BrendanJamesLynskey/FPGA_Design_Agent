# Brief 102: managed projects, stage 1 (records)

What is here, how it was made, and what each file shows. The design is [designs/b102_managed_fcs](../../designs/b102_managed_fcs/README.md);
the concept and the rules are in [docs/managed_projects.md](../../docs/managed_projects.md).

## Records

| File | Made by | Shows |
|---|---|---|
| `demo_session.json` | `python3 designs/b102_managed_fcs/scripts/demo_managed_session.py` | a scripted session through the agent's real tool surface: a request naming a frozen part gets a question, a scoped request edits only the owned controller, and seven attempts on the frozen netlist, the excluded block, the out-of-scope top, a port change, a dropped build source and the manifest are refused |
| `import_check.json` | `python3 flow/managed_import.py check designs/b102_managed_fcs --sim --eqy` | interface, licence and hash, simulation of the functional netlist and the eqy proof against the supplier's RTL |
| `eqy_fault.json` | `flow/managed_import.plant_fault` then the same check | one flipped LUT INIT bit fails both simulation and eqy |
| `eqy_width_scaling.json` | `python3 designs/b102_managed_fcs/scripts/eqy_width_scaling.py` | why the delivered block is 16 bits wide: the open engines of eqy prove 8 and 16 bits and not 64 within the timeout |
| `latency.json` | `python3 designs/b102_managed_fcs/scripts/measure_latency.py` | the verdict latency in clocks of the committed controller and of the agent session's edit, simulated with the CRC block from its functional netlist |
| `builds.json`, `boundary.json` | `flow/run_vivado.sh` and `flow/managed_import.py boundary` (Vivado 2026.1) | the two builds (before and after the edit), their gates, resources and timing, the boundary CDC rows and the boundary timing budgets |

The OSS CAD Suite used was build 20261031 (Yosys 0.70+385); CI pins 20261112, so the numbers here are a local run. No board was used.

## Reproduce

Each row above names its command. They need Python with PyYAML and jsonschema; `import_check`, `eqy_fault`, `eqy_width_scaling` and `latency` also need the
OSS CAD Suite (`FDA_OSS_CAD`) and Icarus Verilog; the two Vivado records need Vivado 2026.1 and a heavy slot (`flow/run_vivado.sh`).

## Known gaps and limits

- The Vivado records (`builds.json`, `boundary.json`) are not in this folder yet: the builds waited for a heavy slot.
- No model drove the session: `demo_session.json` is a script calling the agent's real tool dispatch, so it tests the rules and not a model's behaviour under them.
- The CRC block is 16 bits wide; `eqy_width_scaling.json` shows 32 and 64 bits were not proved within 120 s by the two strategies tried.
- The OSS CAD Suite was build 20261031 here; CI pins 20261112.
- No board was used.
