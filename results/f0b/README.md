# results/f0b

Bring-up of T1 on the owner's Nexys A7-100T (USB-powered), milestone F0B. Builds and runs are all at commit
`4587566`, clean tree, Vivado 2025.2, build stamp `dfd4624e`. The cable serial appears only as its last 4
characters.

| File | What |
|---|---|
| `t1_dimmer_counter_bringup.json` | The last `flow/bringup.py designs/t1_dimmer_counter` run: every step's pass/fail and time, the power gate, tool versions, the ILA comparison results and the rule text |
| `runs/t1_dimmer_counter_<time>.json` | The three recorded runs, same format |
| [t1_dimmer_counter.md](t1_dimmer_counter.md), `t1_dimmer_counter_base.json`, `t1_dimmer_counter_ila.json` | The builds that were programmed (`flow/summarise.py`). The ILA build has two more probes than F0A's (`led` 16 bits, `phase` 8 bits), so its cost differs from `results/f0a` |
| `t1_dimmer_counter_ila_probe_map.txt` | Which signal is on which ILA probe port |
| `captures/` | The first recorded run's raw ILA captures (CSV and VCD, 1024 samples each), the probe maps needed to read them, the capture plan, and the UART test log. CI re-checks these CSVs against `designs/t1_dimmer_counter/hw_checks.py` and shows that corrupted copies fail (`flow/tests/test_hw_flow.py`) |

## The three runs

| Run | Result | Total (s) | discover | program base | UART tests | program ILA | ILA captures |
|---|---|---|---|---|---|---|---|
| 21:45:40 | PASS | 114.6 | 19.9 | 18.1 | 38.7 | 18.0 | 19.3 |
| 21:47:35 | PASS | 111.0 | 16.7 | 18.0 | 38.6 | 18.1 | 19.1 |
| 21:49:26 | PASS | 110.7 | 16.7 | 17.8 | 38.6 | 18.0 | 19.1 |

Each run: power gate (base 0.133 W, ILA 0.149 W total on-chip, vectorless, limit 0.5 W) pass; one target, an
xc7a100t (IDCODE 13631093); DONE pin 1 after each programming; 8 of 8 UART tests passed (0 failed, 0 skipped);
4 of 4 ILA captures passed; the design still answered with the same build stamp and kept the scratch value
written before the captures, with all error counters 0. The ILA results were identical in all three runs: the
COUNT write landed at sample 64 (the trigger position) and the count changed on the next sample; at DUTY 0x08,
0x40 and 0xA0 each lit LED (COUNT 0x8421: LEDs 0, 5, 10, 15) was on for 32, 256 and 640 of the 1024 samples,
equal to `model.led_on_clocks()`, with 0 violations of the per-clock LED rule.
