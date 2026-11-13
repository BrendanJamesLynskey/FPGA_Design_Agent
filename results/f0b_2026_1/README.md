# results/f0b_2026_1

Bring-up of T1 on the owner's Nexys A7-100T (wall power), on the **Vivado 2026.1** builds in
[results/f0a_2026_1](../f0a_2026_1/README.md) (brief 48, 2026-11-11; collected here by brief 49). SRAM programming only,
through `_handoff/board.lock`. The cable serial appears only as its last 4 characters.

## Records

| File | What |
|---|---|
| `t1_dimmer_counter_bringup.json` | The passing `flow/bringup.py designs/t1_dimmer_counter` run: every step's pass/fail and time, the power gate, the ILA comparison results |
| `runs/t1_dimmer_counter_<time>.json` | The two recorded runs, same format: 18:37 failed at `ila_captures` (the `.ltx` lost a bus bit's name, so the hardware manager found no probes; brief 48 added `flow/ltx_fix.py` and rebuilt the ILA bitstream), 19:04 passed |
| [t1_dimmer_counter.md](t1_dimmer_counter.md), `t1_dimmer_counter_base.json`, `t1_dimmer_counter_ila.json` | The builds that were programmed (`flow/summarise.py`; the same files as `results/f0a_2026_1`) |
| `captures/` | The passing run's raw ILA captures (CSV and VCD), the probe maps, the capture plan and the UART test log |

The passing run (its steps 123.5 s in all; the record's wall time 124.0 s): power gate pass (base 0.150 W, ILA 0.161 W total on-chip, vectorless, wall-power limit
2.0 W); 8 of 8 UART tests passed; 4 of 4 ILA captures passed (the COUNT write at sample 64, the trigger position; at DUTY
0x08, 0x40 and 0xA0 each lit LED on for exactly `model.led_on_clocks()` samples, 0 violations); the design still answered
with the same build stamp afterwards. One passing run on this release (the earlier release's record had three in a row).

## Reproduce

`python3 flow/bringup.py designs/t1_dimmer_counter` on the Nexys A7-100T with the board lock held, after building the two variants as in
[results/f0a_2026_1](../f0a_2026_1/README.md). It needs the board and cannot be regenerated without it.

## Known gaps and limits

- One passing run on this release; the first run failed at the ILA captures (the `.ltx` lost a bus bit's name) and was followed by a fix and a rebuild, so the pass is not three in a row.
- SRAM programming only; the flash was not written.
- One board, one design; wall power, so the power gate limit is the wall-power one.
- The owner's manual checks were not repeated on these bitstreams.
