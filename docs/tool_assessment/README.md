# Tool-assessment notes

One page per tool whose output the flow uses as evidence. Each says what the tool is used for, how its output is
checked independently, and its known limits. The question behind each page: if this tool were wrong, would anything
else in the flow notice?

These are our own engineering notes, written in the style of a tool assessment. The standards that ask for such an
assessment are cited only to say what kind of document this is; we have not applied them: DO-254 / ED-80 Section 11
("Additional Considerations": tool assessment and qualification), IEC 61508-3 clause 7.4.4 ("Requirements for support
tools, including programming languages") and ISO 26262-8 clause 11 ("Confidence in the use of software tools"). No
formal qualification of any tool was done, and nothing here is a claim of compliance with any standard.

**Weakest spot:** Vivado's static timing has no second, independent timing tool behind it; see [vivado.md](vivado.md).

| Tool | Kind | Page |
|---|---|---|
| AMD Vivado 2026.1 | design tool (synthesis, implementation, bitstream) and verification tool (timing, DRC, methodology, CDC reports) | [vivado.md](vivado.md) |
| Icarus Verilog | verification tool (simulation) | [icarus.md](icarus.md) |
| Verilator | verification tool (simulation, code coverage, lint) | [verilator.md](verilator.md) |
| SymbiYosys (Yosys, smtbmc, z3) | verification tool (bounded proof, cover) | [symbiyosys.md](symbiyosys.md) |
| cocotb and cocotb-coverage | verification tool (test framework, functional coverage) | [cocotb.md](cocotb.md) |
| Our gates and checkers | verification tools (they decide pass or fail) | [gates.md](gates.md) |

The exact version of every tool that produced a piece of evidence is recorded with it: in `trace.json`
(`inputs.tools`, from the build manifest (`manifest.json`, when the reproducible-build work provides one), else computed) and in each build's `gates.json`
(`vivado_version`).
