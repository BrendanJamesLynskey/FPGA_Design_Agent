# HDL coding standard: FDA-HDL v1.0

**FDA-HDL v1.0** (2026-11-11) is the coding standard for the agent's RTL and for anything a person adds.

Each rule has a short rationale and maps to tool checks:

- Verilator `--lint-only -Wall` warning codes;
- Vivado `report_methodology`, `report_drc` and `report_cdc` rule IDs, read from the build's `gates.json`, at severity
  Warning and above (Info and Advisory do not count);
- the design-standards checker's rules ([design_standards.md](design_standards.md), `flow/standards_check.py`).

The machine-readable copy is `flow/hdl_rules.yaml`. A finding no rule names lands in the catch-all rule of its tool
(`HDL-LINT-00`, `HDL-VIV-00`, `HDL-STD-00`), so nothing is dropped.

```
python3 flow/lint_ruleset.py designs/t1_dimmer_counter --gates designs/t1_dimmer_counter/build/base/gates.json \
    --standards designs/t1_dimmer_counter/build/standards.json --json build/lint/t1.json
```

Each rule ends in one of four states:

| State | Meaning |
|---|---|
| `pass` | its checks ran and found nothing |
| `waived` | every finding is covered by a waiver with owner, reason and date |
| `fail` | at least one finding is not waived |
| `not_run` | none of its tools or reports was available |

The design passes only when no rule fails and every rule was evaluated: a run with a rule `not_run` reports
INCOMPLETE and exits non-zero.

## Rules

| Rule | Title | Rationale | Verilator | Vivado | Standards |
|---|---|---|---|---|---|
| `HDL-SYN-01` | No latches | A latch is level-sensitive storage; static timing analysis handles it with special cases, and in a synchronous design it almost always comes from an incomplete combinational assignment, where simulation can look correct. | `LATCH`, `NOLATCH` | - | `STD-LATCH-01` |
| `HDL-SYN-02` | No combinational loops | A loop through logic has no defined value; simulation may settle where silicon oscillates. | `UNOPTFLAT`, `ALWCOMBORDER` | `LUTLP-*` | `STD-LOOP-01` |
| `HDL-SYN-03` | Complete, non-overlapping case statements | An incomplete case infers a latch or a priority the author did not mean; an overlapping or X case item simulates differently from what synthesis builds. | `CASEINCOMPLETE`, `CASEOVERLAP`, `CASEX`, `CASEWITHX` | - | - |
| `HDL-SYN-04` | Blocking assignments in combinational logic, non-blocking in clocked logic | Mixing them gives race conditions between simulators and a mismatch between simulation and the netlist. | `BLKSEQ`, `COMBDLY`, `BLKANDNBLK`, `ASSIGNDLY`, `INITIALDLY` | - | - |
| `HDL-SYN-05` | One driver per signal | Two drivers is a short in hardware and an X or a last-writer-wins in simulation. | `MULTIDRIVEN`, `PROCASSWIRE`, `CONTASSREG` | `MDRV-*` | - |
| `HDL-SYN-06` | No initial blocks except ROM initialisation | Initial values are not a reset; a design that relies on them cannot be reset back to a known state. | - | - | `STD-INIT-01` |
| `HDL-WID-01` | Widths match | A silent extension or truncation is the commonest arithmetic bug; the reader of the code cannot see it. | `WIDTH`, `WIDTHEXPAND`, `WIDTHTRUNC`, `WIDTHXZEXPAND`, `WIDTHCONCAT`, `SELRANGE`, `ASCRANGE`, `LITENDIAN`, `CMPCONST`, `UNSIGNED` | - | - |
| `HDL-SIG-01` | Every signal is driven and used, every port connected | An undriven signal is a constant the author did not choose; an unused one is often a missed connection. | `UNDRIVEN`, `UNUSED`, `UNUSEDSIGNAL`, `UNUSEDPARAM`, `UNUSEDGENVAR`, `PINMISSING`, `PINCONNECTEMPTY`, `PINNOCONNECT`, `IMPLICIT` | - | - |
| `HDL-CLK-01` | Synchronous design on declared clocks; no derived or gated clocks | A clock made in logic has skew the tools cannot close; a clock enable on the declared clock does the same job safely. Declared domains let the tools and the reviewer see every crossing. | `GENCLK` | `CLKC-*`, `PLHOLDVIO-*` | `STD-CLK-01`, `STD-CLK-02`, `STD-CLK-03` |
| `HDL-RST-01` | Reset as the spec and the reset-strategy skill say; asynchronous inputs synchronised | A reset released asynchronously can leave flip-flops in different states; logic driving an asynchronous reset glitches. | `SYNCASYNCNET`, `CDCRSTLOGIC` | `LUTAR-*` | `STD-RST-01` |
| `HDL-CDC-01` | Every clock-domain crossing through a named, declared primitive | An unsynchronised crossing fails rarely and randomly; only structure, not simulation, shows it. | - | `CDC-*` | `STD-CDC-01`, `STD-CDC-02` |
| `HDL-XDC-01` | Complete timing and I/O constraints | An unconstrained or wrongly constrained path is unchecked by timing analysis, so its slack means nothing. | - | `TIMING-*`, `XDCH-*`, `XDCC-*`, `XDCB-*`, `XDCV-*` | - |
| `HDL-METH-01` | Methodology findings on the synthesised and routed design fixed or waived | The vendor methodology checks are the tool's own list of constructs it handles badly. | - | `SYNTH-*`, `DPIP-*`, `DPOP-*`, `HPDR-*`, `RTRES-*` | `STD-METH-01` |
| `HDL-DRC-01` | No design-rule violation | A DRC error blocks the bitstream or describes an electrical problem on the board. | - | `NSTD-*`, `UCIO-*`, `PDRC-*`, `RTSTAT-*`, `BIVC-*`, `IOSTDTYPE-*`, `REQP-*`, `CFGBVS-*` | - |
| `HDL-IF-01` | Standard interfaces with AMBA names | Standard interfaces make blocks reusable and checkable by protocol checkers. | - | - | `STD-AXI-01`, `STD-AXI-02`, `STD-ARCH-00` |
| `HDL-WAIVE-01` | Every waiver has a reason, an owner and a date | A waiver is a decision; without who and why it cannot be reviewed or revisited. | - | - | `STD-WAIVE-01` |
| `HDL-LINT-00` | Verilator -Wall clean (any warning no other rule maps) | A new Verilator warning code is never dropped for want of a rule; it is fixed or waived with a reason. | `*` | - | - |
| `HDL-VIV-00` | Vivado methodology, DRC and CDC clean (any finding no other rule maps) | A vendor rule ID no other rule names is still fixed or waived with a reason, not ignored. | - | `*` | - |
| `HDL-STD-00` | Design-standards checker clean (any rule no other maps) | A design-standards rule added later still reaches the coding standard instead of being dropped. | - | - | `*` |

## Waivers and changes

Waivers live in `designs/<d>/lint/waivers.yaml`:

```yaml
waivers:
  - rule: HDL-XDC-01
    match: "vivado:XDCH-2@*"          # glob over the finding key (square brackets match literally) or re:<regex>
    reason: <why this finding is accepted>
    owner: <who decided>
    date: 2026-11-11
```

Finding keys are `verilator:CODE file:line`, `vivado:RULE-ID@stage` and `standards:STD-ID file:line`. A waiver without
a reason, owner or date fails `HDL-WAIVE-01`; an unused waiver is listed so it can be removed. A change to a rule bumps
the version here and in `flow/hdl_rules.yaml`.

Results on T1 and two agent-built designs: [results/53_traceability](../results/53_traceability/README.md).
