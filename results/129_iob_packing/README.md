# 129: the I/O-block register packing check, measured

Code: `flow/iob_check.py` (pure, text in and verdict out), `flow/iob_paths.tcl` (the netlist dump, called by `flow/build.tcl` after routing),
gate `iob_packed` in `flow/gates.py` (`_iob_packing`), findings in the check suite's `io` check; tests `flow/tests/test_129_iob_check.py` (real dumps
under `flow/tests/data/iob/`); standard FDA-HDL v1.6 rule HDL-IO-01 ([docs/hdl_coding_standard.md](../../docs/hdl_coding_standard.md)).
Sources read: UG903 v2025.2 p.156 (IOB: "if a setting of IOB true cannot be honored, the Vivado tools generate a critical warning, not an error"),
UG904 v2025.2 p.72 (the placer processes registers with IOB TRUE during clock and I/O placement; a critical warning if it cannot honour it),
UG912 v2025.2 p.227 (IOB on a port or a register), UG571 v1.16 ch. 1 and table 2-19 (UltraScale+ I/O registers are in the bit slice).
These are the 2025.2 documents on disk; the 2026.1 versions were not available, the tool behaviour below is measured on 2026.1.

## What the check does

A register is "meant for the I/O block" when it is marked `IOB TRUE` (RTL attribute, or XDC on the register or on its port) or sits in an interface
declared `iob: true` in the design's `io_interfaces` (the table `flow/io_check.py` reads). After routing the flow dumps, per port, the I/O buffer,
the register next to it, its BEL and site, and what else the nets drive. The register is packed when its BEL is in the I/O logic
(`ILOGICE2.IFF` / `OLOGICE2.OUTFF` on 7-series, `BITSLICE_COMPONENT_RX_TX.IN_FF` / `.OUT_FF` on the K26). Not packed fails the gate
`iob_packed`, with the cell and the reason: Vivado's own message when `vivado.log` has one, else what the netlist shows (a gate between pad and
register, a second load). A design that marks nothing and declares no `iob: true` gets no gate (its gates do not change). An unmarked register
beside a pin of a declared synchronous interface is advice (`IOB-UNMARKED`), never a failure. The older `IO-IOB` of `flow/io_check.py` (interface
level, no reason) is unchanged.

## Vivado's messages (2026.1, as logged)

| Situation | Message |
|---|---|
| 7-series, gate or other non-register between a marked port and its flop (`gate_in`, `gate_out`) | CRITICAL WARNING `[Place 30-722]` Terminal 'ETH_RXD[0]' has IOB constraint set to TRUE, but it is either not connected to a FLOP element or the connected FLOP element could not be brought into the I/O (names the port, not the cell) |
| 7-series, IOB FALSE set on a port whose flop is placed in the I/O block (`unpacked`) | CRITICAL WARNING `[Constraints 18-639]` Setting IOB property to FALSE on port ETH_CRSDV conflicts with the current constrained placement (ILOGIC_X0Y187) on its connected flop u_mac/crs_q_reg. The conflicting constraint will be removed. |
| K26, a marked register behind a gate | WARNING `[Constraints 18-5572]` Instance q_rx1_reg has IOB constraint set, However, the instance does not seem to have valid I/O connection ... will be ignored; CRITICAL WARNING `[Place 30-73]` Invalid constraint on register 'q_rx1_reg'. It has the property IOB=TRUE, but it is not driving or driven by any IO element. (names the cell) |
| both families, a marked register with a second load | INFO `[Synth 8-4163]` Replicating register ... to handle IOB=TRUE attribute (K26 log), or `opt_design` makes a `_lopt_replica` (7-series): the pad register keeps only the pad as its load; no warning, no failure |

report_drc repeats the not-packed cases as Warnings only, which `drc_clean` (Errors and Critical Warnings) ignores: on the Artix-7 `gate_in` (2 rows) and `gate_out` (1 row)
**PLIO-8** "Placement Constraints Check for IO constraints" (`Terminal ETH_RXD[0] has IOB constraint set to TRUE, but it is either not connected to a FLOP element ...`);
on the K26 probe **PLIO-6** (`Invalid constraint on register q_rx1_reg ...`) and **REQP-1617** `use_IOB_register` (`The FDRE cell q_rx1_reg has IOB set to TRUE, but does not
connect directly to an IO cell. Remove the constraint or ensure the FDRE is properly connected to an IO.`). The `unpacked` case (Constraints 18-639) has no DRC row. None of it reaches an existing gate.

## Measurement 1: the RMII network design, Artix-7 (xc7a100tcsg324-1, Vivado 2026.1)

`designs/b63d_nexys_net` (the Nexys A7 RMII trading-path design; constraints from the RMII spec rev 1.2: PHY outputs change 2 to 14 ns after REF_CLK, its
inputs need 4 ns setup and 2 ns hold, both against the forwarded `eth_refclk`). Seven registers sit at the RMII pins: `crs_q`, `er_q`, `rxd_q[1:0]` (rising
edge, sync reset) and `ETH_TXEN`, `ETH_TXD[1:0]` (falling-edge, launch half a clock after the logic clock). `measure_rmii.tcl` reads the design's own
sources and XDC, synthesises, places and routes once per variant (`run_variants.sh` takes a heavy slot; 2 threads, one run at a time, 3 minutes each).
The XDC is read after synthesis (before it, `create_generated_clock -source [get_pins ...]` has no open design in this script; the flow itself differs here).

| Variant | What changed | Check |
|---|---|---|
| `packed` | none (`set_property IOB TRUE` on the RMII ports in design.xdc) | pass, 7/7 packed |
| `unpacked` | `set_property IOB FALSE` on the same ports after the XDC | fail x7 (Constraints 18-639) |
| `gate_in` | planted: `rxd_q <= rmii_rxd & {2{speed_100}}` (an AND before the input flops) | fail x2: ETH_RXD[0], ETH_RXD[1] (Place 30-722); the other 5 stay packed |
| `gate_out` | planted: `ETH_TXEN = txen_q & ~rst` (a gate between the output flop and the pad) | fail x1: ETH_TXEN (Place 30-722) |
| `fanout_out` | ETH_TXEN's register also read by a LED | pass: Vivado duplicated the register (`ETH_TXEN_reg_lopt_replica`); a second load is not a fault on this part |

Numbers (`runs/<variant>/io_times.csv`; worst port of each group; slack in ns; "data path" is the timing path's DATAPATH_DELAY: for an input, pad to the
capturing flop's D pin; for an output, launching flop's clock pin to the pad):

| Variant | Registers in the I/O block | Input setup slack | Input hold slack | Input data path | Output setup slack | Output hold slack | Output data path (clock to pin) | iob check |
|---|---|---|---|---|---|---|---|---|
| packed | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked | 0/7 | +0.801 | +1.883 | 2.266 | +1.011 | +9.430 | 6.953 | FAIL (IOB-NOT-PACKED, 7) |
| gate_in | 5/7 | +0.333 | +1.622 | 2.863 | +3.702 | +8.733 | 4.069 | FAIL (IOB-NOT-PACKED, 2) |
| gate_out | 6/7 | +1.569 | +1.603 | 1.512 | +0.589 | +0.534 | 7.189 | FAIL (IOB-NOT-PACKED, 1) |
| fanout_out | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| packed_Explore | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked_Explore | 0/7 | +0.801 | +1.883 | 2.266 | +1.011 | +9.430 | 6.953 | FAIL (IOB-NOT-PACKED, 7) |
| packed_AltSpreadLogic_high | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked_AltSpreadLogic_high | 0/7 | +0.801 | +1.883 | 2.266 | +1.079 | +9.426 | 6.943 | FAIL (IOB-NOT-PACKED, 7) |

What the numbers say, and what they do not:

- Packing an input removes the routing from the I/O buffer to the flop: data path 1.512 ns (packed) against 2.266 ns (unpacked, 0.754 ns of it net delay); setup slack
  +1.569 against +0.801. Hold goes the other way (+1.603 packed, +1.883 unpacked): the extra delay that costs setup buys hold. The two planted input gates
  (`gate_in`) cost more still: worst input setup +0.333 (data path 2.863 ns), because a LUT and its routing now sit in front of the flop.
- An output flop in the I/O block has a 4.069 ns clock-to-pad path; in the fabric 6.953 ns (2.7 ns of net delay): setup slack +3.702 against +1.011.
  For the output with a gate (`gate_out`) the setup slack is +0.589 and the hold slack falls from +8.733 to +0.534; its hold requirement also changes
  (-11.375 ns to -1.375 ns); I did not investigate why (the falling-edge launch and capture-edge pairing differ once the flop is in a slice).
- Placement dependence is small here: three place directives (default, Explore, AltSpreadLogic_high) gave identical packed numbers and unpacked numbers within
  0.07 ns on the output setup slack (+1.011, +1.011, +1.079). The design is small and the unpacked flops are placed near their pins either way; on a full part the
  spread would be larger, which this measurement does not show. The claim "timing depends on placement" rests on the 0.75 ns and 2.7 ns of routing the fabric flops
  picked up here, not on a measured spread.
- The RMII transmit registers are falling-edge registers (the design's own choice, `always_ff @(negedge clk)`). Packed, they are placed in OLOGIC
  (`OLOGICE2.OUTFF`) like the rising-edge input registers are in ILOGIC: a falling-edge flop does pack on 7-series, with a clock-to-pad path of 4.06 ns.

## Measurement 2: the K26 (xck26-sfvc784-2LV-c, Vivado 2026.1), a probe, not a design of the repo

`k26/iob_probe_k26.sv` on the KR260's RGMII PHY A pins: plain flops marked `(* IOB = "TRUE" *)` and the RGMII IP's IDDRE1 and ODDRE1, one run
(`runs/k26/iob_route.txt`, `iob_messages.txt`). Plain marked flops pack on UltraScale+ too, into the bit slice (`BITSLICE_COMPONENT_RX_TX.IN_FF` for the
input `q_rx0`, `.OUT_FF` for the output `q_tx0` and, after duplication, `q_tx1_reg_rep`); IDDRE1 is `ISERDES` and ODDRE1 is `OSERDES` of the same bit slice
(an ODDRE1 is implemented as OSERDESE3). The gated register `q_rx1_reg` stays in a slice (`SLICEL.DFF`); here the mark is on the register, no port reaches it, so
the check reports `IOB-MARK-ORPHAN` with Vivado's message (the K26 messages differ from the Artix-7 ones, see the table above). Not measured on the K26: timing
(no K26 timing constraints were written for the probe) and the full RGMII design (the 10G trading path was not built: it takes hours of a heavy slot).
The RGMII IP itself needs no `IOB` mark: its IDDR/ODDR primitives are always in the I/O logic.

## Records

`runs/<variant>/` (dump, IOB log lines, per-port timing, check verdict), `runs/k26/`, `measured.md`, the Tcl and shell that made them (`measure_rmii.tcl`, `k26/measure_k26.tcl`, `run_variants.sh`), the K26 probe source (`k26/iob_probe_k26.sv`, `.xdc`), `summarise.py`. Check fixtures: `flow/tests/data/iob/`.

## Reproduce

```
python3 -m pytest -q flow/tests/test_129_iob_check.py                       # no tool needed
# Vivado 2026.1, a heavy slot (the script waits for one and releases only its own lock):
results/129_iob_packing/run_variants.sh "$PWD" /tmp/out packed unpacked gate_in gate_out fanout_out k26
python3 flow/iob_check.py <a build dir with iob_route.txt and vivado.log> --interfaces designs/b63d_nexys_net/build.yaml
```
`runs/<variant>/` holds the dump (`iob_route.txt`), the IOB-related lines of the Vivado log (`iob_messages.txt`), the per-port timing numbers
(`io_times.csv`), `timing_rx.rpt`, `timing_tx.rpt`, and the check's verdict (`iob_summary.json`); `measured.md` is `summarise.py`'s table.

## Known gaps and limits

- One run per variant and per directive; no repeats of the same run (Vivado is deterministic for identical inputs on one machine and version, not shown here).
- The RMII design was measured as synthesised and routed by `measure_rmii.tcl`, not by `flow/run_vivado.sh`; the XDC is read after synthesis.
- The K26 numbers are a probe with no timing. The RGMII design itself (KR260 trading path) was not built.
- Reasons the check can name are the ones Vivado logged (Place 30-722, Place 30-73, Constraints 18-5572/18-639) and two netlist cases (a gate between the pad and
  the register; an output register with a second load). Control-set mismatches (a different clock enable or reset on registers that must share an I/O tile) were not
  produced here; no claim is made about them.
