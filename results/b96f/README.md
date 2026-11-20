# results/b96f: loop-timed transmit and GTH buffer bypass, a feasibility study (brief 96F)

This folder holds the records of brief 96F, a paper and simulation study of steering the KR260 GTH transmit clock to the clock recovered from the partner and bypassing the GT's TX and RX buffers. Nothing ran on a board, in Vivado or in xsim. The study is `designs/b96_kr260_10g/docs/loop_timing_feasibility.md`; the plan for the owner is `designs/b96_kr260_10g/docs/loop_timing_board_test_plan.md`.

## Records
- `loop_timing_model.json`: output of `designs/b96_kr260_10g/model/loop_timing.py`, the behavioural model of the frequency tracker (an acquisition from the existing frequency counter, then a proportional-plus-integral phase loop), scenarios A to F: static offsets, one-sided window, drift across zero, a frequency step, loopback with a phase kick, the counter alone, and the loop-bandwidth trade-off. The assumptions (update rate, jitter, outage) are stated in its `assumptions` entry.
- `latency_prediction.py`, `latency_prediction.json`: the predicted tick-to-trade, echo and loop latency of the loop-timed path against the 97C board medians and the 96E `rm_gp` prediction. The transceiver part is a third-party GTY figure, unconfirmed for this device.

## Reproduce
`python3 designs/b96_kr260_10g/model/loop_timing.py results/b96f/loop_timing_model.json` (about 40 s); `python3 results/b96f/latency_prediction.py results/b96f/latency_prediction.json`; `python3 -m pytest designs/b96_kr260_10g/tests/test_b96f_loop_timing.py` (8 tests, under 2 s, including a check that both records equal a fresh run).

## Known gaps and limits
The model is not a measurement: the update rate, loop delay, measurement jitter and QPLL-reset outage are assumptions, and the behaviour of the GT's phase-alignment circuit under a moving frequency difference, the QPLL's own bandwidth and the CDR are not modelled. The latency prediction inherits an unconfirmed transceiver figure. The KR260 reference-clock source, XAPP1276 and the GTH latency answer record could not be read. No RTL exists for the tracker, the quarter-clock phase detector or the direct crossing.
