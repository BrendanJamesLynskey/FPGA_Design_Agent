# Brief 155: off-chip I/O study results

What an FPGA output does to a 50 ohm line and a receiver, for every LVCMOS DRIVE and SLEW in the banks of our three boards' parts, computed from AMD's own IBIS output models by the time-domain model in `flow/offchip_model.py`: output resistance, termination matrix, best DRIVE with a series resistor, line length, the run on our board designs and a check of the model against the waveforms inside the IBIS files. The reading of these numbers is in [docs/offchip_io.md](../../docs/offchip_io.md).

## Records

| File | What it holds |
|---|---|
| `r_out.csv` | every driver at every corner: launch resistance (pull-up, pull-down, into 50 ohm and into 72 ohm), resistance near the rail, edge times, die capacitance, thresholds, IBIS source |
| `dci_outputs.csv` | the impedance-controlled SSTL/HSTL/POD outputs (OUT40, OUT48, OUT60): slope resistance at VCCO/2 |
| `termination_matrix.csv` | every driver x 10 terminations x 3 corners: overshoot, undershoot, first-incident margin, ringback, settling, receiver edge time |
| `series_r_sweep.csv`, `best_match.json` | every driver x 7 series resistors, judged; the passing combinations and the best three per ranking |
| `proposals_fixed_series.json` | which DRIVE and SLEW pass when 22, 33 or 47 ohm is already on the board |
| `length_sweep.csv` | six configurations against line length |
| `ibis_fixture_check.json` | the driver into IBIS's own fixture against the IBIS waveform: final level and shape error |
| `boards_report.json`, `boards/*.spec.yaml` | the check run on our board designs (the specs hold the assumed loads) |
| `study_parameters.json` | the line, load and model used |

Driver data: AMD's IBIS output models (`artix7.ibs` revision 2.8, IBIS 4.2, 28-AUG-2017; `zynq.ibs` revision 2.8, 27-JAN-2016; `zynquplus.ibs` revision 2.11, IBIS 5.1, 10-FEB-2022; the files shipped with Vivado 2025.2), derived by `tools/ibis_extract.py` into `flow/offchip_data/driver_models.json`; the three corners are the IBIS typ, min (weak: slow process, low VCCO, hot) and max (strong) columns. Line: lossless, Z0 50 ohm, 10 in at er_eff 3.2 (1.52 ns one way); receiver pin and stub 5 pF; receiver thresholds the IBIS Vinl/Vinh of the standard.

## Reproduce

Run these from the repository root in this order. The study needs only Python and the committed driver data; only the extraction needs Vivado's IBIS files on the machine.

```
python3 tools/ibis_extract.py              # needs Vivado's IBIS files; writes flow/offchip_data/driver_models.json (committed)
python3 tools/offchip_study.py              # about 25 minutes, one process; writes the CSV and JSON files here
python3 tools/ibis_fixture_check.py         # the independent check against the IBIS waveforms
python3 tools/offchip_board_report.py       # the run on our board designs
python3 tools/offchip_tables.py             # renders this file from the files above
python3 -m pytest -q flow/tests/test_155_offchip.py
```

## Known gaps and limits

The receiver is not clamped (overshoot is the conservative reading). Package parasitics, loss, crosstalk, multi-drop stubs and simultaneous switching noise are not modelled. The switching ramp is a smooth step calibrated to the IBIS 20-80 % time; against the IBIS waveform it matches the final level within 1 % and the shape within 2 to 8 % rms of the swing for the FAST models and about 15 % for the 7-series SLOW models (see `ibis_fixture_check.json`). IBIS is AMD's own preliminary data, not measured on our boards; no scope trace has been compared with any number here. The board loads in `boards/*.spec.yaml` are assumptions where marked.

## 1. Effective output resistance of an LVCMOS driver

The resistance the wave sees when the driver launches into a 50 ohm load from rest (chord: voltage over current at the launch point). Pull-up and pull-down separately, three corners. It is not one number per DRIVE.

### 7-series HR LVCMOS33 (SLEW FAST; the output resistance is the same for SLOW, only the edge time differs)

| DRIVE mA | launch, strong: pull-up / pull-down ohm | launch, typical | launch, weak | near the rail, typical (0.1 V from the rail it pulls to) | 20-80 % rise ns (typ, 50 ohm fixture) | fall ns | max pull-up mA |
|---|---|---|---|---|---|---|---|
| 4 | 79 / 76 | 96 / 102 | 123 / 146 | 34 / 25 | 0.62 | 0.41 | 25 |
| 8 | 30 / 26 | 41 / 40 | 59 / 68 | 25 / 14 | 0.69 | 0.62 | 44 |
| 12 | 17 / 12 | 22 / 17 | 32 / 32 | 15 / 10 | 0.53 | 0.47 | 63 |
| 16 | 12 / 9 | 15 / 13 | 20 / 22 | 13 / 9 | 0.39 | 0.40 | 89 |

### 7-series HR LVCMOS25 (SLEW FAST; the output resistance is the same for SLOW, only the edge time differs)

| DRIVE mA | launch, strong: pull-up / pull-down ohm | launch, typical | launch, weak | near the rail, typical (0.1 V from the rail it pulls to) | 20-80 % rise ns (typ, 50 ohm fixture) | fall ns | max pull-up mA |
|---|---|---|---|---|---|---|---|
| 4 | 54 / 53 | 69 / 74 | 94 / 112 | 37 / 24 | 1.18 | 0.55 | 22 |
| 8 | 13 / 17 | 16 / 24 | 22 / 42 | 15 / 15 | 0.65 | 0.53 | 61 |
| 12 | 13 / 10 | 16 / 14 | 22 / 22 | 14 / 11 | 0.65 | 0.38 | 61 |
| 16 | 10 / 8 | 12 / 11 | 16 / 17 | 11 / 9 | 0.47 | 0.34 | 81 |

### 7-series HR LVCMOS18 (SLEW FAST; the output resistance is the same for SLOW, only the edge time differs)

| DRIVE mA | launch, strong: pull-up / pull-down ohm | launch, typical | launch, weak | near the rail, typical (0.1 V from the rail it pulls to) | 20-80 % rise ns (typ, 50 ohm fixture) | fall ns | max pull-up mA |
|---|---|---|---|---|---|---|---|
| 4 | 38 / 32 | 51 / 45 | 76 / 70 | 34 / 24 | 0.43 | 0.44 | 22 |
| 8 | 20 / 14 | 26 / 19 | 38 / 29 | 21 / 14 | 0.43 | 0.50 | 37 |
| 12 | 20 / 14 | 26 / 19 | 38 / 29 | 21 / 14 | 0.43 | 0.50 | 37 |
| 16 | 14 / 10 | 18 / 12 | 25 / 18 | 15 / 11 | 0.34 | 0.37 | 52 |
| 24 | 9 / 7 | 12 / 9 | 16 / 12 | 11 / 8 | 0.23 | 0.23 | 76 |

### UltraScale+ HD LVCMOS33 (SLEW FAST; the output resistance is the same for SLOW, only the edge time differs)

| DRIVE mA | launch, strong: pull-up / pull-down ohm | launch, typical | launch, weak | near the rail, typical (0.1 V from the rail it pulls to) | 20-80 % rise ns (typ, 50 ohm fixture) | fall ns | max pull-up mA |
|---|---|---|---|---|---|---|---|
| 4 | 63 / 69 | 72 / 83 | 87 / 106 | 49 / 51 | 0.24 | 0.20 | 57 |
| 8 | 46 / 48 | 54 / 59 | 66 / 80 | 31 / 28 | 0.29 | 0.36 | 76 |
| 12 | 28 / 24 | 34 / 32 | 44 / 48 | 20 / 18 | 0.28 | 0.31 | 99 |
| 16 | 17 / 13 | 20 / 18 | 29 / 30 | 13 / 12 | 0.30 | 0.41 | 127 |

### UltraScale+ HP LVCMOS18 (SLEW FAST; the output resistance is the same for SLOW, only the edge time differs)

| DRIVE mA | launch, strong: pull-up / pull-down ohm | launch, typical | launch, weak | near the rail, typical (0.1 V from the rail it pulls to) | 20-80 % rise ns (typ, 50 ohm fixture) | fall ns | max pull-up mA |
|---|---|---|---|---|---|---|---|
| 2 | 97 / 106 | 112 / 123 | 131 / 147 | 112 / 121 | 0.13 | 0.14 | 30 |
| 4 | 58 / 63 | 67 / 73 | 79 / 87 | 67 / 72 | 0.11 | 0.11 | 50 |
| 6 | 36 / 39 | 42 / 46 | 49 / 54 | 42 / 45 | 0.08 | 0.09 | 80 |
| 8 | 29 / 31 | 34 / 36 | 39 / 43 | 34 / 36 | 0.07 | 0.08 | 100 |
| 12 | 21 / 22 | 24 / 26 | 28 / 31 | 24 / 26 | 0.06 | 0.07 | 139 |

## 2. Impedance-controlled outputs (DCI, UltraScale+ HP, OUTPUT_IMPEDANCE)

| IBIS model (zynquplus.ibs rev 2.11) | strong pull-up / pull-down ohm | typical | weak |
|---|---|---|---|
| HP_SSTL15_DCI_F_OUT40 | 38.4 / 38.8 | 39.8 / 40.5 | 41.6 / 41.5 |
| HP_SSTL15_DCI_F_OUT48 | 46.1 / 46.6 | 47.5 / 48.3 | 49.4 / 49.3 |
| HP_SSTL15_DCI_F_OUT60 | 57.6 / 58.2 | 58.9 / 60.0 | 61.2 / 60.9 |

Slope resistance at VCCO/2, the point an SSTL output works around.

## 3. Termination matrix, LVCMOS33 on 7-series HR, SLEW FAST, 50 ohm line

Worst of the three corners and both edges. `series_N`: N ohm at the source; `parallel_gnd`: 50 ohm to ground at the receiver; `parallel_vtt`: 50 ohm to VCCO/2; `thevenin`: 100 ohm to VCCO and 100 ohm to ground; `ac`: 50 ohm in series with 100 pF to ground.

**Overshoot above VCCO or undershoot below ground at the receiver, V (limit 0.20 V recommended; larger needs the data-sheet duration table)**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 0.38 | 0.21 | 0.14 | 0.07 | 0.00 | 0.00 | 0.12 | 0.00 | 0.00 | 0.00 |
| 8 | 1.12 | 0.86 | 0.69 | 0.42 | 0.05 | 0.01 | 0.19 | 0.00 | 0.00 | 0.03 |
| 12 | 2.12 | 1.42 | 1.13 | 0.75 | 0.26 | 0.01 | 0.32 | 0.02 | 0.02 | 0.19 |
| 16 | 2.42 | 1.61 | 1.27 | 0.86 | 0.34 | 0.00 | 0.41 | 0.16 | 0.16 | 0.50 |

**First-incident-wave margin against VIH/VIL, V (negative: the receiver waits for a reflection)**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | -0.72 | -0.72 | -0.72 | -0.73 | -0.76 | -0.80 | -1.09 | -0.08 | -0.08 | -1.32 |
| 8 | +0.31 | +0.30 | +0.30 | +0.28 | +0.21 | +0.04 | -0.56 | +0.23 | +0.23 | -0.64 |
| 12 | +1.48 | +1.26 | +1.15 | +0.97 | +0.69 | +0.37 | -0.09 | +0.39 | +0.39 | +0.09 |
| 16 | +2.01 | +1.57 | +1.39 | +1.15 | +0.83 | +0.45 | +0.23 | +0.43 | +0.43 | +0.42 |

**Ringback margin against the threshold, V (negative: the edge re-crosses the threshold)**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | -0.07 | -0.02 | -0.01 | -0.01 | +0.00 | +0.00 | +0.01 | -0.11 | -0.11 | +0.00 |
| 8 | +0.00 | +0.00 | +0.00 | +0.01 | +0.01 | +0.00 | -0.04 | +0.01 | +0.01 | +0.00 |
| 12 | -0.68 | +0.01 | +0.00 | +0.01 | +0.00 | +0.00 | +0.01 | +0.01 | +0.01 | +0.01 |
| 16 | -1.08 | -0.04 | +0.01 | +0.02 | +0.00 | +0.00 | +0.00 | +0.01 | +0.01 | +0.00 |

**Settling time to within 5 % of VCCO, ns**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 12.5 | 10.6 | 10.7 | 10.8 | 11.1 | 12.4 | 3.3 | 3.3 | 3.3 | 30.7 |
| 8 | 19.7 | 9.9 | 9.6 | 7.0 | 7.4 | 8.8 | 6.6 | 3.6 | 3.6 | 19.3 |
| 12 | 30.1 | 12.9 | 9.6 | 9.1 | 6.6 | 7.1 | 5.7 | 5.9 | 5.9 | 12.8 |
| 16 | 36.9 | 15.9 | 12.5 | 9.2 | 6.0 | 6.7 | 5.8 | 5.9 | 5.9 | 10.3 |

## 4. The same with SLEW SLOW

**Overshoot or undershoot, V**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 0.31 | 0.18 | 0.13 | 0.06 | 0.00 | 0.00 | 0.08 | 0.00 | 0.00 | 0.00 |
| 8 | 1.13 | 0.85 | 0.67 | 0.42 | 0.06 | 0.01 | 0.13 | 0.00 | 0.00 | 0.03 |
| 12 | 2.09 | 1.40 | 1.11 | 0.74 | 0.25 | 0.01 | 0.23 | 0.00 | 0.00 | 0.18 |
| 16 | 2.32 | 1.53 | 1.21 | 0.82 | 0.32 | 0.00 | 0.21 | 0.05 | 0.05 | 0.39 |

**First-incident-wave margin, V**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | -0.73 | -0.73 | -0.73 | -0.73 | -0.76 | -0.80 | -1.09 | -0.08 | -0.08 | -1.29 |
| 8 | +0.32 | +0.31 | +0.30 | +0.29 | +0.21 | +0.04 | -0.56 | +0.23 | +0.23 | -0.56 |
| 12 | +1.48 | +1.26 | +1.15 | +0.97 | +0.69 | +0.37 | -0.09 | +0.39 | +0.39 | +0.17 |
| 16 | +2.02 | +1.62 | +1.43 | +1.19 | +0.83 | +0.46 | +0.23 | +0.45 | +0.45 | +0.65 |

## 5. UltraScale+ HP LVCMOS18, SLEW FAST (the KR260 RGMII case) 

**Overshoot or undershoot, V**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 |
| 4 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.09 | 0.00 | 0.00 | 0.00 |
| 6 | 0.47 | 0.17 | 0.04 | 0.00 | 0.00 | 0.00 | 0.14 | 0.00 | 0.00 | 0.00 |
| 8 | 0.71 | 0.35 | 0.20 | 0.03 | 0.00 | 0.00 | 0.17 | 0.00 | 0.00 | 0.00 |
| 12 | 1.06 | 0.60 | 0.42 | 0.21 | 0.00 | 0.00 | 0.23 | 0.00 | 0.00 | 0.02 |

**First-incident-wave margin, V**

| DRIVE mA | none | series_10 | series_15 | series_22 | series_33 | series_47 | parallel_gnd | parallel_vtt | thevenin | ac |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | -0.23 | -0.28 | -0.30 | -0.33 | -0.37 | -0.42 | -0.70 | -0.08 | -0.08 | -0.59 |
| 4 | +0.16 | +0.06 | +0.02 | -0.03 | -0.11 | -0.20 | -0.51 | +0.02 | +0.02 | -0.35 |
| 6 | +0.56 | +0.40 | +0.33 | +0.24 | +0.13 | +0.00 | -0.31 | +0.12 | +0.12 | -0.10 |
| 8 | +0.75 | +0.55 | +0.47 | +0.37 | +0.23 | +0.09 | -0.21 | +0.17 | +0.17 | +0.01 |
| 12 | +1.02 | +0.77 | +0.67 | +0.54 | +0.37 | +0.20 | -0.07 | +0.23 | +0.23 | +0.18 |

## 6. Best DRIVE plus series resistor on a 50 ohm line

From `series_r_sweep.csv`: every DRIVE, SLEW and E-series resistor (0, 10, 15, 22, 27, 33, 47 ohm) judged at all three corners. A combination **passes** when it has no `OFFCHIP-*` flag (receiver within VCCO + 0.2 V and GND - 0.2 V, no ringback through the threshold), a first-incident-wave margin of at least 0.1 V over VIH/VIL at every corner, and a weak-corner receiver 20-80 % time of at most 2.5 ns (a quarter of a 10 ns unit interval). Z0 50 ohm, 10 in, 5 pF, unclamped receiver.

### 7-series HR LVCMOS33: 4 of 56 combinations pass

| DRIVE / SLEW | 0 ohm | 10 ohm | 15 ohm | 22 ohm | 27 ohm | 33 ohm | 47 ohm |
|---|---|---|---|---|---|---|---|
| 4 mA SLOW | first-wave+overshoot | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 4 mA FAST | first-wave+overshoot+ringback | first-wave+overshoot+ringback | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave | first-wave |
| 8 mA SLOW | overshoot | overshoot | overshoot | overshoot | overshoot | first/rise | first/rise |
| 8 mA FAST | overshoot | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 12 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | first/rise |
| 12 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 16 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 16 mA FAST | overshoot+ringback | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass |

| ranking | choice | R_out typ pu / pd (chord into Z0 + R) | R_out + R typ | total, strong corner | total, weak corner | worst mismatch % | worst overshoot V | first-incident margin V | rx rise ns strong | rx rise ns weak |
|---|---|---|---|---|---|---|---|---|---|---|
| smallest worst-corner mismatch | 16 mA SLOW + 47 ohm | 13.1 / 10.5 | 60.1 / 57.5 | 58 / 55 | 64 / 62 | 28.0 | -0.0 | 0.461 | 0.578 | 1.236 |
| smallest worst-corner mismatch | 16 mA FAST + 47 ohm | 13.2 / 10.2 | 60.2 / 57.2 | 58 / 55 | 64 / 63 | 28.0 | -0.0 | 0.446 | 0.499 | 0.778 |
| fastest receiver edge | 16 mA FAST + 47 ohm | 13.2 / 10.2 | 60.2 / 57.2 | 58 / 55 | 64 / 63 | 28.0 | -0.0 | 0.446 | 0.499 | 0.778 |
| fastest receiver edge | 12 mA FAST + 47 ohm | 17.5 / 13 | 64.5 / 60 | 61 / 57 | 70 / 66 | 40.3 | 0.01 | 0.368 | 0.658 | 1.157 |
| slowest edge | 8 mA FAST + 33 ohm | 28.1 / 22.6 | 61.1 / 55.6 | 55 / 49 | 72 / 73 | 46.4 | 0.01 | 0.209 | 0.698 | 1.516 |
| slowest edge | 12 mA FAST + 47 ohm | 17.5 / 13 | 64.5 / 60 | 61 / 57 | 70 / 66 | 40.3 | 0.01 | 0.368 | 0.658 | 1.157 |

### 7-series HR LVCMOS25: 8 of 56 combinations pass

| DRIVE / SLEW | 0 ohm | 10 ohm | 15 ohm | 22 ohm | 27 ohm | 33 ohm | 47 ohm |
|---|---|---|---|---|---|---|---|
| 4 mA SLOW | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 4 mA FAST | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 8 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | pass |
| 8 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | pass |
| 12 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 12 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 16 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 16 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |

| ranking | choice | R_out typ pu / pd (chord into Z0 + R) | R_out + R typ | total, strong corner | total, weak corner | worst mismatch % | worst overshoot V | first-incident margin V | rx rise ns strong | rx rise ns weak |
|---|---|---|---|---|---|---|---|---|---|---|
| smallest worst-corner mismatch | 16 mA FAST + 47 ohm | 11.2 / 9.8 | 58.2 / 56.8 | 56 / 55 | 61 / 61 | 22.5 | -0.004 | 0.435 | 0.538 | 0.937 |
| smallest worst-corner mismatch | 16 mA SLOW + 47 ohm | 11.2 / 9.8 | 58.2 / 56.8 | 56 / 55 | 61 / 61 | 22.8 | -0.004 | 0.436 | 0.558 | 1.037 |
| fastest receiver edge | 16 mA FAST + 47 ohm | 11.2 / 9.8 | 58.2 / 56.8 | 56 / 55 | 61 / 61 | 22.5 | -0.004 | 0.435 | 0.538 | 0.937 |
| fastest receiver edge | 16 mA SLOW + 47 ohm | 11.2 / 9.8 | 58.2 / 56.8 | 56 / 55 | 61 / 61 | 22.8 | -0.004 | 0.436 | 0.558 | 1.037 |
| slowest edge | 12 mA SLOW + 47 ohm | 14.6 / 11.7 | 61.6 / 58.7 | 59 / 56 | 66 / 64 | 32.0 | -0.0 | 0.348 | 0.698 | 1.795 |
| slowest edge | 8 mA SLOW + 47 ohm | 14.5 / 17.6 | 61.5 / 64.6 | 59 / 60 | 66 / 74 | 47.9 | -0.004 | 0.242 | 0.698 | 1.795 |

### 7-series HR LVCMOS18: 10 of 70 combinations pass

| DRIVE / SLEW | 0 ohm | 10 ohm | 15 ohm | 22 ohm | 27 ohm | 33 ohm | 47 ohm |
|---|---|---|---|---|---|---|---|
| 4 mA SLOW | overshoot | overshoot | first/rise | first/rise | first/rise | first-wave | first-wave |
| 4 mA FAST | overshoot | overshoot | first/rise | first/rise | first/rise | first-wave | first-wave |
| 8 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 8 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 12 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 12 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 16 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | pass |
| 16 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | pass | pass |
| 24 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 24 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |

| ranking | choice | R_out typ pu / pd (chord into Z0 + R) | R_out + R typ | total, strong corner | total, weak corner | worst mismatch % | worst overshoot V | first-incident margin V | rx rise ns strong | rx rise ns weak |
|---|---|---|---|---|---|---|---|---|---|---|
| smallest worst-corner mismatch | 16 mA SLOW + 33 ohm | 16.4 / 11.5 | 49.4 / 44.5 | 46 / 42 | 56 / 49 | 15.7 | 0.077 | 0.45 | 0.479 | 0.838 |
| smallest worst-corner mismatch | 16 mA FAST + 33 ohm | 16.4 / 11.5 | 49.4 / 44.5 | 46 / 42 | 56 / 49 | 15.7 | 0.084 | 0.45 | 0.419 | 0.658 |
| fastest receiver edge | 24 mA FAST + 47 ohm | 10.9 / 8.1 | 57.9 / 55.1 | 56 / 54 | 62 / 58 | 23.4 | 0.0 | 0.361 | 0.459 | 0.638 |
| fastest receiver edge | 16 mA FAST + 33 ohm | 16.4 / 11.5 | 49.4 / 44.5 | 46 / 42 | 56 / 49 | 15.7 | 0.084 | 0.45 | 0.419 | 0.658 |
| slowest edge | 8 mA SLOW + 33 ohm | 23.4 / 16.4 | 56.4 / 49.4 | 52 / 46 | 66 / 57 | 31.4 | 0.001 | 0.308 | 0.618 | 1.197 |
| slowest edge | 12 mA SLOW + 33 ohm | 23.4 / 16.4 | 56.4 / 49.4 | 52 / 46 | 66 / 57 | 31.4 | 0.001 | 0.308 | 0.618 | 1.197 |

### UltraScale+ HD LVCMOS33: 4 of 56 combinations pass

| DRIVE / SLEW | 0 ohm | 10 ohm | 15 ohm | 22 ohm | 27 ohm | 33 ohm | 47 ohm |
|---|---|---|---|---|---|---|---|
| 4 mA SLOW | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 4 mA FAST | first-wave+ringback | first-wave+ringback | first-wave | first-wave | first-wave | first-wave | first-wave |
| 8 mA SLOW | first/rise | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 8 mA FAST | first/rise | first-wave | first-wave | first-wave | first-wave | first-wave | first-wave |
| 12 mA SLOW | overshoot | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 12 mA FAST | overshoot | overshoot | overshoot | overshoot | overshoot | pass | first/rise |
| 16 mA SLOW | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |
| 16 mA FAST | overshoot+ringback | overshoot | overshoot | overshoot | overshoot | overshoot | pass |

| ranking | choice | R_out typ pu / pd (chord into Z0 + R) | R_out + R typ | total, strong corner | total, weak corner | worst mismatch % | worst overshoot V | first-incident margin V | rx rise ns strong | rx rise ns weak |
|---|---|---|---|---|---|---|---|---|---|---|
| smallest worst-corner mismatch | 16 mA FAST + 47 ohm | 14.8 / 13.1 | 61.8 / 60.1 | 59 / 57 | 69 / 68 | 37.4 | -0.0 | 0.328 | 0.499 | 0.818 |
| smallest worst-corner mismatch | 12 mA SLOW + 33 ohm | 25.3 / 23.1 | 58.3 / 56.1 | 54 / 50 | 68 / 69 | 37.5 | 0.003 | 0.304 | 0.558 | 1.177 |
| fastest receiver edge | 12 mA FAST + 33 ohm | 25.4 / 23.1 | 58.4 / 56.1 | 53 / 50 | 68 / 69 | 37.5 | -0.001 | 0.308 | 0.439 | 0.778 |
| fastest receiver edge | 16 mA FAST + 47 ohm | 14.8 / 13.1 | 61.8 / 60.1 | 59 / 57 | 69 / 68 | 37.4 | -0.0 | 0.328 | 0.499 | 0.818 |
| slowest edge | 16 mA SLOW + 47 ohm | 14.8 / 13.1 | 61.8 / 60.1 | 60 / 57 | 69 / 68 | 38.4 | -0.001 | 0.328 | 0.598 | 1.177 |
| slowest edge | 12 mA SLOW + 33 ohm | 25.3 / 23.1 | 58.3 / 56.1 | 54 / 50 | 68 / 69 | 37.5 | 0.003 | 0.304 | 0.558 | 1.177 |

### UltraScale+ HP LVCMOS18: 30 of 105 combinations pass

| DRIVE / SLEW | 0 ohm | 10 ohm | 15 ohm | 22 ohm | 27 ohm | 33 ohm | 47 ohm |
|---|---|---|---|---|---|---|---|
| 2 mA SLOW | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave | first-wave | first-wave | first-wave+ringback |
| 2 mA MEDIUM | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave | first-wave | first-wave | first-wave+ringback |
| 2 mA FAST | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave | first-wave | first-wave | first-wave+ringback |
| 4 mA SLOW | first/rise | first/rise | ringback | first-wave | first-wave+ringback | first-wave+ringback | first-wave |
| 4 mA MEDIUM | first/rise | ringback | ringback | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave+ringback |
| 4 mA FAST | first/rise | ringback | ringback | first-wave+ringback | first-wave+ringback | first-wave+ringback | first-wave+ringback |
| 6 mA SLOW | overshoot | pass | pass | pass | first/rise | first/rise | ringback |
| 6 mA MEDIUM | overshoot | pass | pass | pass | first/rise | first/rise | ringback |
| 6 mA FAST | overshoot | pass | pass | pass | first/rise | first/rise | ringback |
| 8 mA SLOW | overshoot | overshoot | pass | pass | pass | pass | first/rise |
| 8 mA MEDIUM | overshoot | overshoot | pass | pass | pass | pass | first/rise |
| 8 mA FAST | overshoot | overshoot | overshoot | pass | pass | pass | first/rise |
| 12 mA SLOW | overshoot | overshoot | overshoot | pass | pass | pass | first/rise |
| 12 mA MEDIUM | overshoot | overshoot | overshoot | pass | pass | pass | pass |
| 12 mA FAST | overshoot | overshoot | overshoot | overshoot | pass | pass | pass |

| ranking | choice | R_out typ pu / pd (chord into Z0 + R) | R_out + R typ | total, strong corner | total, weak corner | worst mismatch % | worst overshoot V | first-incident margin V | rx rise ns strong | rx rise ns weak |
|---|---|---|---|---|---|---|---|---|---|---|
| smallest worst-corner mismatch | 12 mA SLOW + 22 ohm | 24 / 25.9 | 46 / 47.9 | 43 / 44 | 50 / 53 | 14.5 | 0.158 | 0.541 | 0.499 | 0.798 |
| smallest worst-corner mismatch | 12 mA MEDIUM + 22 ohm | 24 / 25.9 | 46 / 47.9 | 43 / 44 | 50 / 53 | 14.5 | 0.175 | 0.541 | 0.339 | 0.459 |
| fastest receiver edge | 12 mA FAST + 27 ohm | 24 / 25.9 | 51 / 52.9 | 48 / 49 | 55 / 58 | 15.4 | 0.083 | 0.459 | 0.335 | 0.412 |
| fastest receiver edge | 12 mA MEDIUM + 22 ohm | 24 / 25.9 | 46 / 47.9 | 43 / 44 | 50 / 53 | 14.5 | 0.175 | 0.541 | 0.339 | 0.459 |
| slowest edge | 12 mA MEDIUM + 47 ohm | 24 / 25.9 | 71 / 72.9 | 68 / 69 | 75 / 78 | 55.4 | 0.0 | 0.199 | 0.718 | 2.054 |
| slowest edge | 12 mA FAST + 47 ohm | 24 / 25.9 | 71 / 72.9 | 68 / 69 | 75 / 78 | 55.4 | 0.0 | 0.199 | 0.652 | 1.904 |


## 7. Line length

| standard | DRIVE | SLEW | R series | length in | delay ns | overshoot V | undershoot V | first-incident margin V | staircase visible | ringback margin V | settle ns |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LVCMOS33 | 12 | SLOW | 22.0 | 1.0 | 0.152 | 0.036 | 0.112 | 0.973 | False | 0.002 | 7.14 |
| LVCMOS33 | 12 | SLOW | 22.0 | 3.0 | 0.455 | 0.358 | 0.485 | 0.973 | False | 0.008 | 7.51 |
| LVCMOS33 | 12 | SLOW | 22.0 | 6.0 | 0.909 | 0.493 | 0.686 | 0.973 | True | 0.003 | 8.05 |
| LVCMOS33 | 12 | SLOW | 22.0 | 10.0 | 1.516 | 0.515 | 0.739 | 0.973 | True | 0.005 | 9.33 |
| LVCMOS33 | 12 | SLOW | 22.0 | 15.0 | 2.273 | 0.516 | 0.742 | 0.973 | True | 0.005 | 13.12 |
| LVCMOS33 | 12 | FAST | 22.0 | 1.0 | 0.152 | 0.033 | 0.167 | 0.973 | False | 0.001 | 2.5 |
| LVCMOS33 | 12 | FAST | 22.0 | 3.0 | 0.455 | 0.397 | 0.595 | 0.973 | True | 0.027 | 3.2 |
| LVCMOS33 | 12 | FAST | 22.0 | 6.0 | 0.909 | 0.511 | 0.733 | 0.973 | True | 0.01 | 6.09 |
| LVCMOS33 | 12 | FAST | 22.0 | 10.0 | 1.516 | 0.521 | 0.748 | 0.973 | True | 0.012 | 9.13 |
| LVCMOS33 | 12 | FAST | 22.0 | 15.0 | 2.273 | 0.521 | 0.748 | 0.973 | True | 0.012 | 12.92 |
| LVCMOS33 | 8 | FAST | 33.0 | 1.0 | 0.152 | 0.01 | 0.005 | 0.209 | False | 0.006 | 3.26 |
| LVCMOS33 | 8 | FAST | 33.0 | 3.0 | 0.455 | 0.01 | 0.009 | 0.209 | True | 0.008 | 4.19 |
| LVCMOS33 | 8 | FAST | 33.0 | 6.0 | 0.909 | 0.01 | 0.041 | 0.209 | True | 0.001 | 5.54 |
| LVCMOS33 | 8 | FAST | 33.0 | 10.0 | 1.516 | 0.01 | 0.048 | 0.209 | True | 0.007 | 7.36 |
| LVCMOS33 | 8 | FAST | 33.0 | 15.0 | 2.273 | 0.01 | 0.05 | 0.209 | True | 0.007 | 9.63 |
| LVCMOS33 | 16 | FAST | 0.0 | 1.0 | 0.152 | 1.222 | 1.188 | 2.006 | False | 0.034 | 4.34 |
| LVCMOS33 | 16 | FAST | 0.0 | 3.0 | 0.455 | 2.14 | 2.178 | 2.006 | True | -0.837 | 13.09 |
| LVCMOS33 | 16 | FAST | 0.0 | 6.0 | 0.909 | 2.273 | 2.409 | 2.006 | True | -1.07 | 24.2 |
| LVCMOS33 | 16 | FAST | 0.0 | 10.0 | 1.516 | 2.277 | 2.423 | 2.006 | True | -1.083 | 36.91 |
| LVCMOS33 | 16 | FAST | 0.0 | 15.0 | 2.273 | 2.277 | 2.423 | 2.006 | True | -1.083 | 52.63 |
| LVCMOS33 | 12 | FAST | 0.0 | 1.0 | 0.152 | 0.567 | 0.832 | 1.484 | False | 0.036 | 3.85 |
| LVCMOS33 | 12 | FAST | 0.0 | 3.0 | 0.455 | 1.451 | 1.768 | 1.484 | True | -0.451 | 10.66 |
| LVCMOS33 | 12 | FAST | 0.0 | 6.0 | 0.909 | 1.701 | 2.087 | 1.484 | True | -0.67 | 19.73 |
| LVCMOS33 | 12 | FAST | 0.0 | 10.0 | 1.516 | 1.717 | 2.117 | 1.484 | True | -0.683 | 30.07 |
| LVCMOS33 | 12 | FAST | 0.0 | 15.0 | 2.273 | 1.717 | 2.117 | 1.484 | True | -0.683 | 42.88 |
| LVCMOS33 | 4 | FAST | 0.0 | 1.0 | 0.152 | 0.012 | 0.018 | -0.721 | False | 0.003 | 3.79 |
| LVCMOS33 | 4 | FAST | 0.0 | 3.0 | 0.455 | 0.149 | 0.327 | -0.721 | True | 0.005 | 5.24 |
| LVCMOS33 | 4 | FAST | 0.0 | 6.0 | 0.909 | 0.219 | 0.377 | -0.721 | True | -0.08 | 8.2 |
| LVCMOS33 | 4 | FAST | 0.0 | 10.0 | 1.516 | 0.224 | 0.379 | -0.721 | True | -0.075 | 12.46 |
| LVCMOS33 | 4 | FAST | 0.0 | 15.0 | 2.273 | 0.224 | 0.379 | -0.721 | True | -0.075 | 17.77 |

