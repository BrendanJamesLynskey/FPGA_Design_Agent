# Brief 102: managed projects, stage 3 (records)

One real third-party block inside a managed project: Alex Forencich's parallel CRC/LFSR (`rtl/lfsr.v` of verilog-ethernet, MIT, commit
`77320a9471d19c7dd383914bc049e02d9f4f1ffb`), vendored unmodified and frozen, with our own adapter around it. The design is
[designs/b102_managed_ext](../../designs/b102_managed_ext/README.md); the rules are in [docs/managed_projects.md](../../docs/managed_projects.md) ("Stage 3").

## Records

| File | Made by | Shows |
|---|---|---|
| `import_check.json` | `python3 flow/managed_rtl_import.py check designs/b102_managed_ext --upstream <clone> --out ...` | provenance complete; each vendored file equal to the bytes at the upstream commit; interface equal to the contract at the instantiated parameters; the block matching a CRC-32 step model (2,000 random vectors at each of 8, 16, 32, 64 data bits); the adapter plus the block matching the register model; a planted fault in a copy of the block rejected by both simulations |
| `demo_session.json` | `FDA_102_RECORD=1 python3 -m pytest -q flow/tests/test_102_stage3.py -k scripted` | a scripted session through the agent's real tool dispatch: a request about the frozen block alone gets a question; a scoped request edits only the owned controller; seven attempts on the vendored files, an out-of-scope file, the manifest and a build.yaml that drops the block are refused; the design simulated before and after with the block compiled in |
| `build_base/`, `builds.json` | `flow/run_vivado.sh designs/b102_managed_ext base` (Vivado 2026.1, one thread) | every gate passes; resources, timing, power, run time and peak memory |
| `boundary.json` | `flow/managed_import.boundary_cdc` on the build's `cdc_synth.rpt` | no CDC row touches the adapter |
| `trust.json`, `provenance.md`, `provenance.json` | `agent/core/managed.py` (`trust`, `write_provenance`) | per component: theirs or ours, origin, licence, hash, files, and the computed trust label |
| `import_check_eqy.json` | the same command with `--eqy` | the equivalence attempt of the adapter plus the block against our own specification (see Known gaps) |

## Reproduce

The import check and the scripted session need Python with PyYAML and jsonschema, Icarus Verilog and git; `--upstream` needs a clone of
`https://github.com/alexforencich/verilog-ethernet` (the commit above is in `provenance` of `project.yaml`); `--eqy` needs the OSS CAD Suite
(`FDA_OSS_CAD`). The build needs Vivado 2026.1 and a heavy slot (`flow/run_vivado.sh`). The scripted session runs under pytest because outside it the
agent's access gate needs the access key.

## Known gaps and limits

- The block's own upstream tests were not run: the only ones that cover it are MyHDL co-simulations of the Ethernet modules that use it, which need MyHDL's
  Icarus plug-in built from source (not approved here). Our simulations are random-vector, not exhaustive; only the 16-bit instance is built.
- The build ran once (no seeds); the 6.206 ns constraint is on the 25 MHz oscillator pin for a timing study; no board was used and the power figure is vectorless.
- The scripted session is not a model: no LLM-driven run on a managed project yet.
- `eqy` against our specification: see `import_check_eqy.json`; the earlier 32 and 64-bit scaling null of stage 1 suggests XOR-heavy CRC logic is hard for its open engines.
- The upstream comparison proves the files equal the bytes at the commit in a clone the checker is given; it does not prove the commit is on the upstream's main branch.
