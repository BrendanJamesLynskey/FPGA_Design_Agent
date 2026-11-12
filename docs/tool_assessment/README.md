# Tool-assessment notes (brief 53)

One page per tool whose output the flow uses as evidence. Each says what the tool is trusted for, how its output is
checked independently, and its known limits. The question behind each page: if this tool were wrong, would anything
else in the flow notice? These notes are our own engineering assessment, written in the style of a tool assessment
(DO-254 / ED-80 Section 11, IEC 61508-3 7.4.4, ISO 26262-8 clause 11, by title only). No tool here is qualified, and
nothing here is a claim of compliance with any standard.

| Tool | Kind | Page |
|---|---|---|
| AMD Vivado 2026.1 | design tool (synthesis, implementation, bitstream) and verification tool (timing, DRC, methodology, CDC reports) | [vivado.md](vivado.md) |
| Icarus Verilog | verification tool (simulation) | [icarus.md](icarus.md) |
| Verilator | verification tool (simulation, code coverage, lint) | [verilator.md](verilator.md) |
| SymbiYosys (Yosys, smtbmc, z3) | verification tool (bounded proof, cover) | [symbiyosys.md](symbiyosys.md) |
| cocotb and cocotb-coverage | verification tool (test framework, functional coverage) | [cocotb.md](cocotb.md) |
| Our gates and checkers | verification tools (they decide pass or fail) | [gates.md](gates.md) |

The exact version of every tool that produced a piece of evidence is recorded with it: in `trace.json`
(`inputs.tools`, from brief 54's manifest when it exists, else computed) and in each build's `gates.json`
(`vivado_version`).
