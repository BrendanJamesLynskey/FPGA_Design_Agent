# eqy_default: the RATE_MATCH = 0 core is main 6909e43f's core (brief 96C, addendum 2)

The owner's decision of 2026-11-19 made brief 96C's elastic buffer a build option with the old path as the default. This folder shows that the default is the old design, formally,
by `eqy` (Yosys equivalence checking, OSS CAD Suite, `yosys-slang` front end, SymbiYosys with bitwuzla): gold is `b96_core` of main 6909e43f read straight from git, gate is `b96_core` of this branch at `RATE_MATCH = 0` (default),
both with the same wrapper, `--top b96_core`.

    results/b96c/eqy_default/run.sh default     # base core against main's base core
    results/b96c/eqy_default/run.sh all3        # lat_all3's files with GO_REG = 0 against main's lat_all3 files
    results/b96c/eqy_default/run.sh mutant      # a planted change (the MAC's error counter counts by 2): must FAIL

About 5 to 7 minutes each, no Vivado, no board. Records: `result_<mode>.txt` (the verdict), `partitions_<mode>.txt` (every partition), `gate_edits.diff` (the four edits below).

## What the proof covers

`eqy` cuts both designs at the registers whose names match and proves each cone of logic between them equal by induction (depth 2), so it proves **every register's next-state logic, every output and every input to the GT black box equal**, for any input sequence,
without a bounded depth. The old receive path sits in this branch under the generate block `g_old`; the script drops that prefix from the gate's names so the registers match main's names (`u_rx.u_td...`). Result in the table below: all partitions proved, and the planted change fails in the partition it touches.

| Mode | Result | Partitions |
|---|---|---|
| default | **PASS**: designs equivalent (`result_default.txt`) | 219 proved, 0 failed |
| all3 | **PASS**: designs equivalent (`result_all3.txt`) | 218 proved, 0 failed |
| mutant (a planted `c_err` increment of 2) | **FAIL**, as it must (`result_mutant.txt`) | 218 proved, 1 failed: `b96_core.u_rx.c_err` |

## What it does not cover (limits, stated)

1. **The XPM clock-crossing macros are wires in this proof** (`xpm_wire.sv`: one stand-in, the same on both sides): `eqy` cannot prove anything about a clock crossing, and a black box with parameter-dependent port widths is not read correctly by the slang front end. So the proof does **not** cover a crossing's own parameters:
   in particular `GO_REG` (the go-pulse crossing's `REG_OUTPUT`, 1 on main, 0 in `lat_all3`) is invisible to it; the `all3` run proves that the *logic* around the crossing is main's `lat_all3` logic, and `GO_REG = 0` is checked by reading `build.yaml`/`b96_core.sv` and by the simulation below.
2. **The GT Wizard core is a black box** (its outputs free, the same on both sides); the new ports `txbufstatus_out` and `rxbufstatus_out` exist only in the gate's black box.
3. **Four edits to the gate's copy of `b96_core.sv`** (`gate_edits.diff`, made by `run.sh` from the worktree file): the `TXPPM` (0x01C) write and read lines and the `GT_BUF` (0x020) read line, which are registers 96C added that main's core does not have (their reset values are 0, and 97C had no such addresses: both read 0 there and ignore writes);
   and the receive snapshot's read window cut back from 29 to 18 words (RXV18 to RXV28 are the 96C words, driven 0 when `RATE_MATCH = 0`: they read 0, as main's core, which did not decode those addresses, did). The proof is therefore of the core **without those five new features**; the features are covered by the core bench at the default
   (`tests/core_cocotb_default.py`: `default_has_no_rate_match_words` reads FEATURES and RXV18 to RXV28; the new registers are exercised by `tests/core_cocotb.py` and the host tests) and by the board run of the rate-matched builds, which carry the same two registers.
4. The old receive path sits in the branch under the generate block `g_old`; `run.sh` drops that prefix from 498 of the gate's wire names (none collides with another) so its registers match main's by name. A register the rename missed would have no partner and show as a failed or unmatched partition, not a pass; the mutant run shows the matching works (the failure is in the very register touched).
5. The proof is of the RTL, not of the netlist Vivado builds from it: the default rebuild's gates (`results/b96c/builds/control/`) and the board runs of 97C and 96C cover that side.

Where the formal proof cannot reach (the crossings), the regression the brief names is the core bench at the default: `tests/core_cocotb_default.py` is main 6909e43f's own `core_cocotb.py` (97C's seven order-sequence tests included) with only the hierarchy paths moved
to the generate block; it measures 11 clocks from the GT word of the price to the GT word of the order and no spread in the echo (`results/b96c/core_sim_default.json`, the same numbers as 97C).
