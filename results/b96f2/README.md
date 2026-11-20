# results/b96f2: loop-timing sources (brief 96F2), paper only; nothing ran on a board, in synthesis or in simulation

Records for `designs/b96_kr260_10g/docs/loop_timing_sources.md`: the Transceiver Wizard example design generated once from Vivado 2026.1 so its bypass-controller drive could be read.

## Records

- `probe5.tcl`: generates the Wizard 1.7 example design for the b96 bypass core (in-core QPLL, and `LOCATE_COMMON = EXAMPLE_DESIGN`); no synthesis or implementation.
- `probe5.txt`: its log (every step returned 0; scratch paths shortened).
- The generated example sources carry AMD's copyright header and are **not** committed.

What was read from the generated files (line numbers are in the 2026.1 output; regenerate to check):
- `*_example_top.v` lines 509 to 521: TX controller reset = `~userclk_tx_active` through a reset synchroniser on `TXUSRCLK2`; RX controller reset = `~userclk_rx_active || ~buffbypass_tx_done` on `RXUSRCLK2`; both `start_user_in` tied 0 (lines 165, 185).
- `*_example_top.v` lines 535 to 549 and `*_example_init.v`: done is ANDed into the init-done inputs; 30,000 us TX and 130,000 us RX timers; `error` only to VIO probes 12 and 13.
- `ip/*/synth/*.v`: `.txpippmpd_in(1'H1)` and `.txoutclksel_in(3'H5)` in the bypass core, against `1'H0` and `3'H2` in the buffers-on core of build `rm_gp`.
- `*_example_wrapper.v` (outside-QPLL variant): the COMMON wrapper's `SDM0DATA`, `SDM0RESET`, `SDM0TOGGLE`, `SDM0WIDTH` tied to 0; `QPLL0RESET` from `gtwiz_reset_qpll0reset_out`; the `.xdc` files of the two variants are identical.

## Known gaps and limits

These are file readings, not measurements. XAPP1276 was read as the Japanese translation (English not retrievable); AR 68177, AR 64309 and AR 69011 were not retrievable. See section 8 of the note.

## Reproduce

`vivado -mode batch -source results/b96f2/probe5.tcl -tclargs <scratch dir>` (Vivado 2026.1, about 30 s, about 1.9 GB).
