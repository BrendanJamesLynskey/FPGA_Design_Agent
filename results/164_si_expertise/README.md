# Brief 164: the data behind the signal-integrity plots and the two-answer check

Receiver waveforms and the per-port two answers (as built, optimal) for the Expertise page's "Signal integrity at the pins" drawer. Everything here is a **model result on AMD's preliminary IBIS data (brief 155's solver), not a scope measurement**. Reading page: [docs/offchip_drive_slew.md](../../docs/offchip_drive_slew.md) section 10.

## Records

| File | What it holds |
|---|---|
| `waveforms_series_r.csv` | the receiver voltage of one 50 ohm, 6 in, 5 pF line for LVCMOS33 (7-series HR) and LVCMOS18 (UltraScale+ HP), DRIVE 12 FAST, strong IBIS corner, series 0, 22, 33 and 47 ohm; rising and falling edge, 0.1 ns samples; the data sheet limits, thresholds, IBIS model, file and revision on every row |
| `kr260_two_answers.json` | for KR260 port A and B, with brief 155's assumed 4 in and brief 162's measured carrier lengths: the XDC setting, the best DRIVE and SLEW as built (no resistor) and the optimal setup, each with its peaks, time beyond the 0.2 V limit, verdict, passing combinations and what it still fails |
| `kr260_waveforms.csv` | the receiver waveform of each of those settings (strong corner, rising and falling edge) |
| `kr260_carrier_data_no_flags.check.{json,txt}` | brief 162's carrier-data check run with no `--family`, `--part` or `--bank-type` (the spec's own keys); its findings equal brief 162's committed run; the text and JSON now also carry the two answers per group |

## Reproduce

Run from the repository root (about 3 minutes each, one process, no Vivado; the committed driver data is enough).

```
python3 tools/si_expertise_data.py
python3 flow/offchip_check.py --spec results/162_kr260_si/kr260_b58a_trigger_carrier_data.spec.yaml --xdc designs/b58a_trigger/design.xdc --json results/164_si_expertise/kr260_carrier_data_no_flags.check.json
python3 -m pytest -q flow/tests/test_164_si.py
python3 site/export.py && python3 site/build.py --check      # the plots are drawn from these files by site/si_figures.py
```

## Known gaps and limits

The same as brief 162's: preliminary IBIS tables, carrier copper only (no SOM routing), Z0 from the fabricator's table, one line model (`er_eff` 3.2), no clamp diodes, DCI and `OUTPUT_IMPEDANCE` not simulated, ngspice disagrees on falling edges with nothing in series. "Best as built" assumes nothing is in series on the board. The weak-corner edge rule (a quarter of the unit interval) is a house assumption.
