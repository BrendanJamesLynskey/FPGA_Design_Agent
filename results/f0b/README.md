# results/f0b

Measured on 2025.2, superseded by [results/f0b_2026_1](../f0b_2026_1/README.md).
Still current: `manual_checks.md` (the owner's checks on these bitstreams; not repeated on 2026.1).

Bring-up of T1 on the owner's Nexys A7-100T (USB-powered), milestone F0B. Builds and runs are all at commit
`4587566`, clean tree, Vivado 2025.2, build stamp `dfd4624e`. The cable serial appears only as its last 4
characters.

## Records

| File | What |
|---|---|
| `t1_dimmer_counter_bringup.json` | The last `flow/bringup.py designs/t1_dimmer_counter` run: every step's pass/fail and time, the power gate, tool versions, the ILA comparison results and the rule text |
| `runs/t1_dimmer_counter_<time>.json` | The three recorded runs, same format |
| [t1_dimmer_counter.md](t1_dimmer_counter.md), `t1_dimmer_counter_base.json`, `t1_dimmer_counter_ila.json` | The builds that were programmed (`flow/summarise.py`). The ILA build has two more probes than F0A's (`led` 16 bits, `phase` 8 bits), so its cost differs from `results/f0a` |
| `t1_dimmer_counter_ila_probe_map.txt` | Which signal is on which ILA probe port |
| `captures/` | The first recorded run's raw ILA captures (CSV and VCD, 1024 samples each), the probe maps needed to read them, the capture plan, and the UART test log. CI re-checks these CSVs against `designs/t1_dimmer_counter/hw_checks.py` and shows that corrupted copies fail (`flow/tests/test_hw_flow.py`) |

## The three runs: figures withdrawn

The three recorded runs (all PASS: eight of eight UART tests and four of four ILA captures each, the same ILA results in all
three) were made on bitstreams from an earlier Vivado release and on USB power. Their timings and power figures cannot be
re-measured, so they are withdrawn from this README rather than relabelled; the raw records stay in
`runs/` and `t1_dimmer_counter_bringup.json`. The current bring-up result, on the Vivado 2026.1 builds and wall power, is in
[results/f0b_2026_1](../f0b_2026_1/README.md).

## Reproduce

`python3 flow/bringup.py designs/t1_dimmer_counter` on the Nexys A7-100T with the board lock held (SRAM programming over JTAG). It
programs the builds of [results/f0a](../f0a/README.md) and needs the board; with the current install it writes the Vivado 2026.1
records in [results/f0b_2026_1](../f0b_2026_1/README.md) instead of these.

## Known gaps and limits

- Superseded by [results/f0b_2026_1](../f0b_2026_1/README.md); these bitstreams came from an earlier Vivado release.
- Three runs in a row on one board and one design; the runs differ only in time.
- USB power here, not wall power; the power gate limit differs from the 2026.1 run.
- `manual_checks.md` (the owner's checks of these bitstreams) was not repeated on the 2026.1 bitstreams.
