# HDL coding standard: FDA-HDL v1.2

**FDA-HDL v1.2** (2026-11-14; v1.0 of 2026-11-12 was the first release, v1.1 of the same day added the check suite's rules) is the coding standard for the agent's RTL and for anything a person adds. v1.1 (brief 71) splits the reset rule into HDL-RST-01 to HDL-RST-05 after the owner's rule that resets are synchronous, adds the check suite's rules (HDL-CLK-02, HDL-IF-02, HDL-IF-03, HDL-VER-01, HDL-GT-01, HDL-DOC-01), and gives every rule a one-line `fix` and a KB `skill`, which the [check suite](check_suite.md) shows with each finding. v1.2 (brief 73) adds HDL-IF-04 to HDL-IF-06 for the AXI4-Lite interface profiles (the `axi_profile` check).

Each rule has a short rationale and maps to tool checks:

- Verilator `--lint-only -Wall` warning codes;
- Vivado `report_methodology`, `report_drc` and `report_cdc` rule IDs, read from the build's `gates.json`, at severity
  Warning and above (Info and Advisory do not count);
- the design-standards checker's rules ([design_standards.md](design_standards.md), `flow/standards_check.py`);
- the check suite's own codes ([check_suite.md](check_suite.md), `flow/checks`): the reset netlist scan, the structural
  CDC check, the exception and I/O checks, the MMCM range check, FSM coverage, AMD IP notes, the link plan and the DOC
  gate. `flow/lint_ruleset.py` reads the reset codes from a check-suite result (`--checks build/checks/base/synth.json`);
  rules whose checks are only other suite checks are reported by the suite, not by `lint_ruleset.py`.

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

| Rule | Title | Rationale | Verilator | Vivado | Standards | Check suite |
|---|---|---|---|---|---|---|
| `HDL-SYN-01` | No latches | A latch is level-sensitive storage; static timing analysis handles it with special cases, and in a synchronous design it almost always comes from an incomplete combinational assignment, where simulation can look correct. | `LATCH`, `NOLATCH` | - | `STD-LATCH-01` | - |
| `HDL-SYN-02` | No combinational loops | A loop through logic has no defined value; simulation may settle where silicon oscillates. | `UNOPTFLAT`, `ALWCOMBORDER` | `LUTLP-*` | `STD-LOOP-01` | - |
| `HDL-SYN-03` | Complete, non-overlapping case statements | An incomplete case infers a latch or a priority the author did not mean; an overlapping or X case item simulates differently from what synthesis builds. | `CASEINCOMPLETE`, `CASEOVERLAP`, `CASEX`, `CASEWITHX` | - | - | - |
| `HDL-SYN-04` | Blocking assignments in combinational logic, non-blocking in clocked logic | Mixing them gives race conditions between simulators and a mismatch between simulation and the netlist. | `BLKSEQ`, `COMBDLY`, `BLKANDNBLK`, `ASSIGNDLY`, `INITIALDLY` | - | - | - |
| `HDL-SYN-05` | One driver per signal | Two drivers is a short in hardware and an X or a last-writer-wins in simulation. | `MULTIDRIVEN`, `PROCASSWIRE`, `CONTASSREG` | `MDRV-*` | - | - |
| `HDL-SYN-06` | No initial blocks except ROM initialisation | Initial values are not a reset; a design that relies on them cannot be reset back to a known state. | - | - | `STD-INIT-01` | - |
| `HDL-WID-01` | Widths match | A silent extension or truncation is the commonest arithmetic bug; the reader of the code cannot see it. | `WIDTH`, `WIDTHEXPAND`, `WIDTHTRUNC`, `WIDTHXZEXPAND`, `WIDTHCONCAT`, `SELRANGE`, `ASCRANGE`, `LITENDIAN`, `CMPCONST`, `UNSIGNED` | - | - | - |
| `HDL-SIG-01` | Every signal is driven and used, every port connected | An undriven signal is a constant the author did not choose; an unused one is often a missed connection. | `UNDRIVEN`, `UNUSED`, `UNUSEDSIGNAL`, `UNUSEDPARAM`, `UNUSEDGENVAR`, `PINMISSING`, `PINCONNECTEMPTY`, `PINNOCONNECT`, `IMPLICIT` | - | - | - |
| `HDL-CLK-01` | Synchronous design on declared clocks; no derived or gated clocks | A clock made in logic has skew the tools cannot close; a clock enable on the declared clock does the same job safely. Declared domains let the tools and the reviewer see every crossing. | `GENCLK` | `CLKC-*`, `PLHOLDVIO-*` | `STD-CLK-01`, `STD-CLK-02`, `STD-CLK-03` | - |
| `HDL-CLK-02` | MMCM and PLL settings inside the data sheet's VCO and PFD ranges | Neither report_drc nor report_methodology rejects a hand-instantiated MMCME2 or PLLE2 outside its VCO or PFD range (measured, brief 18); the clock then does not lock or drifts on the board. | - | - | - | clocking: `CMT-RANGE-01` |
| `HDL-RST-01` | Synchronous resets; an asynchronous reset only in a reset synchroniser or from a declared external asynchronous input | AMD recommends synchronous resets (UG949); an asynchronous reset is released at an arbitrary time relative to the clock and stops registers packing into DSP and block RAM. The owner's rule (2026-11-13) allows it only in reset and CDC synchronisers and where an external device's reset is asynchronous. | `SYNCASYNCNET` | `ROAS-*` | `STD-RST-01` | resets: `RST-ASYNC-01` |
| `HDL-RST-02` | One polarity per reset | A reset used active high in one place and active low in another becomes two nets and two control sets, which costs placement freedom and invites a mismatched release. | - | - | - | resets: `RST-POL-01`, `RST-POL-02` |
| `HDL-RST-03` | No asynchronous reset on a register that belongs in a DSP or block RAM | The DSP48 and block-RAM registers have synchronous resets only, so an asynchronous reset keeps the register in the fabric, costing flip-flops and the primitive's fast internal path. | - | `DPIR-*`, `DPOR-*`, `RMIR-*`, `RMOR-*`, `RROR-*` | - | resets: `RST-DSPRAM-01` |
| `HDL-RST-04` | A reset enters each clock domain through a synchroniser | A reset made in one clock domain and released in another without a synchroniser can release different registers on different cycles, or violate recovery and removal timing. | - | `CDC-7`, `CDC-8` | - | resets: `RST-CDC-01` |
| `HDL-RST-05` | No logic drives an asynchronous reset | A glitch on combinational logic driving an asynchronous reset resets the register; AMD's methodology check LUTAR-1 flags it. | `CDCRSTLOGIC` | `LUTAR-*` | - | resets: `RST-LUT-01` |
| `HDL-CDC-01` | Every clock-domain crossing through a named, declared primitive | An unsynchronised crossing fails rarely and randomly; only structure, not simulation, shows it. | - | `CDC-*` | `STD-CDC-01`, `STD-CDC-02` | cdc_structure: `U*` |
| `HDL-XDC-01` | Complete timing and I/O constraints | An unconstrained or wrongly constrained path is unchecked by timing analysis, so its slack means nothing. | - | `TIMING-*`, `XDCH-*`, `XDCC-*`, `XDCB-*`, `XDCV-*` | - | exceptions: `EXC-*`; io: `IO-*` |
| `HDL-METH-01` | Methodology findings on the synthesised and routed design fixed or waived | The vendor methodology checks are the tool's own list of constructs it handles badly. | - | `SYNTH-*`, `DPIP-*`, `DPOP-*`, `HPDR-*`, `RTRES-*`, `RBOR-*`, `ULMTCS-*` | `STD-METH-01` | - |
| `HDL-DRC-01` | No design-rule violation | A DRC error blocks the bitstream or describes an electrical problem on the board. | - | `NSTD-*`, `UCIO-*`, `PDRC-*`, `RTSTAT-*`, `BIVC-*`, `IOSTDTYPE-*`, `REQP-*`, `CFGBVS-*` | - | - |
| `HDL-IF-01` | Standard interfaces with AMBA names | Standard interfaces make blocks reusable and checkable by protocol checkers. | - | - | `STD-AXI-01`, `STD-AXI-02`, `STD-ARCH-00` | - |
| `HDL-WAIVE-01` | Every waiver has a reason, an owner and a date | A waiver is a decision; without who and why it cannot be reviewed or revisited. | - | - | `STD-WAIVE-01` | - |
| `HDL-IF-02` | AMD AXI4-Lite IP next to our register blocks is used with its measured conventions in mind | AMD's AXI4-Lite peripherals answer holes with OKAY, ignore byte strobes, alias registers and may pop on read (measured, brief 69); software written for our blocks' conventions misbehaves on them. Advice, not a failure. | - | - | - | axi: `AXI-AMD-IP` |
| `HDL-IF-03` | Every accepted AXI request gets exactly one response within a bounded wait | A slave that drops a response hangs the master for ever (the AXI DMA register port returned one B for two writes, brief 69); no other rule of the checker sees a response that never comes. | - | - | - | axi_checker: `RESP_LOST` |
| `HDL-IF-04` | A generated AXI4-Lite register block has the interface profile its design declares and behaves as it says | A profile (house, amd_compatible, strict) fixes what a driver writer could guess wrong (holes, strobes, unaligned and reserved accesses, the error capture). A block that claims one and behaves as another, or a map that names a profile its design did not choose, gives software wrong expectations that no protocol checker sees. | - | - | - | axi_profile: `AXI-PROFILE-SPEC`, `AXI-PROFILE-MISMATCH`, `AXI-PROFILE-DRIFT`, `AXI-PROFILE-OVERRIDE`, `AXI-PROFILE-STALE`, `AXI-PROFILE-NOSRC` |
| `HDL-IF-05` | A design that mixes interface profiles says so | One design with a strict block and a house block gives the driver two sets of rules; the datasheets state each, but the design should state the mix. A block generated before profiles existed states no profile at all. | - | - | - | axi_profile: `AXI-PROFILE-MIX` |
| `HDL-IF-06` | AMD IP in a design with a strict AXI4-Lite profile is acknowledged | AMD's AXI4-Lite peripherals answer holes with OKAY and read 0, ignore byte strobes and accept unaligned addresses (measured, brief 69); a driver written for strict blocks expects SLVERR and must allow for that. Advice, not a failure. | - | - | - | axi_profile: `AXI-PROFILE-AMD-STRICT` |
| `HDL-VER-01` | Every FSM state and listed transition is covered in simulation | A state or transition never reached in simulation is behaviour no test has checked; the coverage comes from the trace, not from the simulator's own coverage (none of the free simulators has FSM coverage). | - | - | - | fsm: `FSM-STATE`, `FSM-TRANS`, `FSM-UNLISTED` |
| `HDL-GT-01` | A transceiver link the part, speed grade and board can build | A line rate outside the speed grade's window, a reference the board does not provide or more lanes than it has cannot be built; the plan says so before any RTL is written. | - | - | - | gt: `GT-PLAN` |
| `HDL-DOC-01` | The design's handover documents what was built, verified and measured | The next engineer needs every number traced to a record and every gap stated (owner, 2026-11-13; the DOC gate of brief 68). | - | - | - | doc: `DOC-PROBLEM` |
| `HDL-LINT-00` | Verilator -Wall clean (any warning no other rule maps) | A new Verilator warning code is never dropped for want of a rule; it is fixed or waived with a reason. | `*` | - | - | - |
| `HDL-VIV-00` | Vivado methodology, DRC and CDC clean (any finding no other rule maps) | A vendor rule ID no other rule names is still fixed or waived with a reason, not ignored. | - | `*` | - | - |
| `HDL-STD-00` | Design-standards checker clean (any rule no other maps) | A design-standards rule added later still reaches the coding standard instead of being dropped. | - | - | `*` | - |

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
the version here and in `flow/hdl_rules.yaml`. The rule table above is generated from `flow/hdl_rules.yaml`; each rule's `fix` and `skill` are there.

Results on T1 and two agent-built designs: [results/53_traceability](../results/53_traceability/README.md).
