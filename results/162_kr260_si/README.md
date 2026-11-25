# Brief 162: KR260 carrier board data and the DRIVE, SLEW and series-resistor sweep

Per-net routed lengths of the KR260 carrier's PL-facing nets (read from AMD's Allegro board file; only derived numbers are kept here), a calibrated Z0 and delay for its stack-up, the brief 155 check re-run with those lengths, a DRIVE x SLEW x series-R sweep on a 50 ohm line of 1, 3, 6 and 10 inches, an ngspice cross-check of the solver, and a check of newer AMD IBIS files. Reading page: [docs/offchip_drive_slew.md](../../docs/offchip_drive_slew.md).

## Records

| File | What it holds |
|---|---|
| `kr260_net_lengths.csv` | per-net total length (mil and inches), vias, copper per layer and trace width for the RGMII (PHY2 on HPA, PHY3 on HPB), Pmod, PHY side, FTDI UART and SFP-control nets; carrier copper only (not the SOM, not the package) |
| `z0.json` | the calibrated laminate Dk, microstrip Z0 and delay by an analytic formula and by `Matrix_Articles/si_models/fdm2d.py`, and the stripline delay |
| `kr260_b58a_trigger_assumed.check.{json,txt}` | the brief 155 check on `designs/b58a_trigger` with brief 155's assumed 4 in, 4 pF lines (`--family zynquplus --part xck26-sfvc784-2LV-c --bank-type HP --propose`) |
| `kr260_b58a_trigger_carrier_data.spec.yaml`, `.check.{json,txt}` | the same with the carrier's measured lengths (port A 7.2 in, port B 2.8 in) and the DP83867's 5 pF |
| `drive_slew_sweep.csv` | 868 rows: DRIVE x SLEW x series R (0, 10, 15, 22, 27, 33, 47 ohm) x length (1, 3, 6, 10 in), 50 ohm, 5 pF, three IBIS corners: overshoot, undershoot, first-incident margin, ringback, settling, receiver edge time, pass/fail and flags, IBIS model and file revision |
| `ngspice_check.csv` | 48 cases (rising and falling, three corners) simulated by brief 155's solver and by ngspice 47: peak, trough, 20-80 % time, settling and the waveform difference |
| `ibis_revision_check.csv` | `zynquplus.ibs` rev 2.11 against `kintexuplus.ibs` rev 2.15 (Vivado 2026.1): resistance, edge time and die capacitance of the HP LVCMOS18 models at three corners |

## Reproduce

Run from the repository root. Only the sweep, the ngspice check, the Z0 script and the IBIS comparison run on a clean checkout with Vivado's IBIS files and (for ngspice) a user-local ngspice build; the net lengths need a dump of AMD's board file that is not in the repository.

```
python3 tools/offchip_drive_slew_sweep.py        # about 45 minutes, one process; writes drive_slew_sweep.csv
python3 tools/kr260_z0.py                        # about 3 minutes (field solver); writes z0.json
python3 tools/offchip_ngspice.py                 # needs ngspice (BSD-3-Clause) at ~/.local/opt/ngspice-47/bin/ngspice; about 15 minutes
python3 tools/ibis_rev_compare.py                # needs the two Vivado data directories named in its header
python3 tools/kr260_nets_summary.py --dump <dir>  # <dir> holds nets.csv and net_vias.csv from a local parse of BRD_05101_01_rev_b01_aa.brd
python3 -m pytest -q flow/tests/test_162_kr260_si.py
```

The parse used KiCad 10's Allegro importer source (GPL-3, `pcbnew/pcb_io/allegro/convert/`), compiled stand-alone with shim headers and a small dumper in a scratch directory; neither it nor AMD's `.brd`, schematic or BOM is committed. AMD's IBIS files are not committed either (see `THIRD_PARTY_NOTICES.md`).

## Known gaps and limits

Model results on AMD's preliminary IBIS data; nothing here is a scope measurement. Carrier lengths exclude the K26 SOM's routing and the package. The laminate Dk is calibrated from the board's fab table because the file has none, and the analytic and field-solver calibrations differ (Dk 3.2 against 5.1), so delays are given as a range. ngspice and the solver agree to a few millivolts with a series resistor and on rising edges, but disagree by up to 0.59 V on falling edges with nothing in series (cause not found). The series-resistor survey counted one board only. The sweep covers 7-series HR LVCMOS33 and LVCMOS25 and UltraScale+ HP LVCMOS18, on one line (`er_eff` 3.2, 5 pF).
