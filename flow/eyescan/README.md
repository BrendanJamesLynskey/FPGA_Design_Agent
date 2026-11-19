# flow.eyescan: on-chip RX eye scan for a GTH link (brief 96D)

Measures the receiver's own sampling margin with the GTHE4 transceiver's eye-scan counters, writes every point's raw counts to a capture file, derives eye width, height
and bathtub curves from those counts, and draws them (static SVG and an interactive page). Hardware side: `designs/b96_kr260_10g` built with `EYESCAN = 1` (the `eyescan/`
build); the host sequence below is the one of UG576 v1.7.1 chapter 4, "RX Margin Analysis".

## What the eye is (read this first)

The GTH receiver compares a second, offset sampler with its data sampler **after the equaliser** (LPM or DFE). The result is a *statistical eye of the margin inside the
receiver*, built from error counts. It is **not** the eye a scope would show at the pins, and it says nothing about the transmitter's output, the optical eye, TX jitter or
anything before the equaliser. On the short, clean optical loop of this design it says little about lossy copper channels. Every plot, page and tool output says "after the
equaliser" for this reason.

## Commands

```
python -m flow.eyescan probe  --serial <cable serial>                    READ-ONLY: build features, the DRP words, RXOUT_DIV, equaliser. No write, no laser.
python -m flow.eyescan run    --serial S --lock-text "96D: ..." --out DIR --name NAME [--eq lpm|dfe|keep] [--target-ber 1e-9] [--hstep 2] [--vstep 8] [--vmax 120]
                              [--tx-diff N] [--tx-pre N] [--tx-post N] [--partial FILE]       (board: the owner runs it, through _handoff/board.lock)
python -m flow.eyescan run    --fake --out DIR --name NAME ...            OFFLINE: the SYNTHETIC statistical eye of flow/eyescan/fake.py (never a measurement)
python -m flow.eyescan plot   CAPTURE.json [-o DIR] [--ber 1e-9]            eye heat map and horizontal bathtub, SVG
python -m flow.eyescan page   A.json [B.json] -o page.html                 interactive page; two captures enable the Compare tab
python -m flow.eyescan compare A.json B.json [--ber 1e-9]                   width, height, open points side by side
python -m flow.eyescan api    CAPTURE.json --what summary|eye|bathtub|surface|margin|page [--ber 1e-9]
python -m flow.eyescan serve  CAPTURE.json|PARTIAL.jsonl [--port 8765]      the page plus a live JSON feed (for a scan in progress, `run --partial`)
```

The board run for this brief is `_handoff/fpga_agent/run_96d_stage3.sh` (program SRAM, probe, scans in a fixed order, plots, summary). `run` refuses a lock text that does not
start `96D:`, a `--tx-diff` above the shipped 11000 (873 mVppd) and a cursor above 12 (3.1 dB).

## The hardware path

| Piece | Where | Behaviour |
|---|---|---|
| `es_ctrl.sv` | `designs/b96_kr260_10g/rtl/` | DRP master plus a point sequencer in the free-running 100 MHz clock (the GT's DRPCLK). One access at a time. A command that arrives while busy is ignored and sets `rejected`. |
| Registers | `docs/register_map.md`: DRP_ADDR 0x024, DRP_DATA 0x028, ES_CMD 0x02C, ES_STAT 0x030, ES_POINT 0x034, ES_TMO 0x038, ES_RES 0x03C, GT_DRIVE 0x084 | read 0 and ignore writes in a build without `EYESCAN` (FEATURES bit 4) |
| `es.xdc` | `designs/b96_kr260_10g/` | sets `ES_EYE_SCAN_EN` and `ES_ERRDET_EN` in the bitstream: the Wizard leaves both FALSE, and enabling them later through the DRP needs a PMA reset (UG576 Table 4-20) |
| Static attributes | host, once per scan | `ES_QUALIFIER` 0, `ES_QUAL_MASK` all ones (every cycle counts), `ES_SDATA_MASK` for the 32-bit internal width: words `00FF 0000 FF00 FFFF FFFF` (UG576 Table 4-20: `{40'b1, 32'b0, 8'b1}`) |
| One point | `es_ctrl` | read-modify-write 0x04F (horizontal), 0x097 (vertical word), 0x03C (prescale, then run); poll 0x253 for END (0101); read 0x251 errors and 0x252 samples; clear run |
| Save and restore | host (`hw.py`) | every DRP word the scan touches is read first and written back and **read again** at the end; `restore.ok` in the capture says whether every word matched. The sequencer itself does not restore. |
| Equaliser, TX drive | host | `--eq` writes GT_CTRL bit 6 and pulses RXDFELPMRESET (GT_DRIVE bit 16); both the equaliser and the TX drive are put back at the end of a scan, also after an error |

## Units, and what to multiply by what

| Quantity | Value | Source |
|---|---|---|
| Horizontal step | 1/64 UI per count at 10.3125 Gb/s (RXOUT_DIV 1: full rate, +-32 counts is +-0.5 UI); the default grid steps 2 counts, so 1/32 UI | UG576 Table 4-20; RXOUT_DIV read from DRP 0x063 |
| Vertical step | one code = 1.5, 1.8, 2.2 or 2.8 mV for `RX_EYESCAN_VS_RANGE` 0 to 3 (the scan uses 0); **nominal**, from the guide, not calibrated on this part | UG576 Table 4-20 |
| Bits per point | `samples x 2^(1+prescale) x 32` (32 = the receiver's internal data width; the 16-bit sample counter saturates at 65535) | UG576 Table 4-20 describes the prescale and counters; the 32 and the product are this host's reading of them, **to be confirmed on the board** |
| BER | `errors / bits`; with no errors, "below 3/bits" (95 % one-sided bound), never 0 | rule of three |
| DFE | two measurements per offset (UT sign 0 and 1); the merged point adds their errors and bits | UG576 chapter 4 text before Table 4-19 |
| Error and sample counts | saturate at 65535 | UG576 Table 4-20 |

### Time cost (at 10.3125 Gb/s; hardware time of one clean point, computed by `scan.estimate_seconds`)

| Target BER | Longest rung (prescale) | Clean-point time | Full default grid (33 x 31 points, about 35 % of them clean) |
|---|---|---|---|
| 1e-6 | 0 | 0.0004 s | host overhead only (a few minutes) |
| 1e-7 | 3 | 0.003 s | host overhead only |
| 1e-9 | 10 | 0.65 s (ladder 0, 3, 6, 9, 10) | about 4 minutes of hardware plus about 5 of host overhead |
| 1e-10 | 13 | 5.2 s | about 30 minutes |
| 1e-12 | 15, repeated 22 times | 295 s | about 29 hours: scan a few rows only (`--hstep`, `--vmax`) |

Host overhead is about 6 JTAG register operations a point at a few tens of milliseconds each (a planning figure; the capture records the real count and time).

## Things a user could get wrong

- **Post-equaliser.** See above. A wide eye here does not mean a clean signal at the pins.
- **BER floor.** A point can only vouch for a depth its bits reach. The page and the API count a zero-error point whose bits are too few as *shallow*, not open. Width and height at a depth are
  computed from open points only, so a scan to 1e-9 read at 1e-12 shows no eye (it says so) rather than a wrong one.
- **The ladder and the final prescale.** A point runs prescale 0, 3, 6, ... until a rung sees `--min-errors` (10) errors or the target depth is reached. Its BER is from the rungs at its final prescale
  (repeats of the last rung are pooled; earlier rungs are not). Points near the eye edge therefore have fewer bits than clean ones: that is deliberate and recorded per point.
- **Grid resolution.** Width and height are spans between grid points, so they carry one grid step of uncertainty (the plots print it); this is not a statistical error bar.
- **LPM and DFE are not interchangeable.** DFE doubles the points (two UT signs) and its adaptation needs enough transitions in the data; the idle blocks of the 10GBASE-R link are scrambled, which gives that.
- **mV.** The vertical axis is in nominal mV from UG576's range table; the receiver was not calibrated against an instrument.
- **A scan can disturb the link.** The scan writes eye-scan DRP words and may re-adapt the equaliser (`--eq`); it checks the link between rows and records `link.ok_throughout`. A capture with that false is
  not to be quoted.
- **Synthetic captures.** `run --fake` and the files under `results/b96d/offline/` come from an invented eye model. They carry `synthetic: true`, `instrument.mock: true`, a SYNTHETIC watermark and a banner,
  and the `eye_scan` agent tool never passes them. They test the software, not the link.
- **Changing the TX drive.** The sweep keeps TXDIFFCTRL at or below the shipped 11000 (873 mVppd) and cursors at or below 3.1 dB, so the module's input is never driven harder than the design always drove it. A
  lower swing can close the eye or drop the link; the capture records the link state.

## Capture format "fda-capture-eye/1"

Envelope as the common capture format (`debug_core/capture.py`, "fda-capture/1"): `schema`, `instrument {kind, driver, settings, mock}`, `design`, `build`, `conditions {start, end}` (SYSMON temperature and
VCCINT/VCCAUX/VCCBRAM with the DS925 windows), `created`. Payload: `settings` (line rate, equaliser, RXOUT_DIV, UI per count, RANGE, grid, target depth, prescale rungs, TX drive, measured ppm), `attributes_before`
(the saved DRP words), `restore {ok, mismatch}`, `link {before, after, rows_ok, ok_throughout}`, `gt` (buffer status, module DDM), `run {seconds, register_ops, points_done, error}` and `points`: one entry per
(h, v, UT) with its rungs `{pre, err, samp, tmo}`. Nothing derived is stored as a measurement; `capture.py` computes BER, width, height, bathtub and surface from the counts.

## API (what the navigator reuses)

`flow/eyescan/api.py`: `summary`, `eye(cap, depth)`, `bathtub(cap, axis)`, `surface(cap)` (log10 BER grid with the zero-error flags), `margin(cap, depth, min_width_ui, min_height_mv)` and `page_data(cap)` (everything the
interactive page draws). The agent tool `eye_scan` (`agent/core/eye_tools.py`) wraps `margin`; it reads a capture and never runs the board.

## Verified and not verified

Verified in simulation and by tests: the RTL's register layout and DRP traffic against the Python twin (`tests/eyescan_cocotb.py`); the host against a register-level synthetic board (`flow/tests/test_eyescan.py`); the
derived numbers against the model the synthetic counts were drawn from. **Not verified until a board run:** that the real GTHE4 answers these DRP accesses as UG576 describes, the 32-bit reading of "bits per sample",
the SDATA mask for this width, and every number of every real eye.

## Known gaps (from the one review of brief 96D; the RTL was built before the review and is not changed)

- **`es_ctrl` continues after a DRP timeout.** If an access gets no DRDY the sequencer still runs its read-modify-writes on stale data; the host sees `drp_tmo` and records an error, and `restore` repairs the words, but the sequencer does not abort. Fix needs an RTL change and a rebuild.
- **`ES_POINT` and `ES_TMO` are read live during a point.** Do not write them while `ES_STAT` bit 0 is set (the host never does).
- **JSON `ber: 0.0` means no errors seen**, not a BER of zero: read `ber_ub` (the 3/bits bound). Plots show it correctly.
- **Contours and bathtub lines are drawn between grid points** (marching squares, straight segments); a gap of unmeasured points is bridged in the bathtub. The numbers (width, height, open/closed) come from the points only.
- **A saved partial capture** (a scan that stopped) has `run.error` set and fewer points than `settings.expected_points`; `api.margin` and the `eye_scan` tool refuse to pass it.
- **`serve` with a partial file** needs a `<name>.partial.header.json` that `run` does not write yet; `serve` on a finished capture works.
- **The data-width check** only tests `RX_INT_DATAWIDTH == 1` (32 or 40 bit); the masks assume 32 (this build). A 40-bit build would need new masks.
- **After a reset in the middle of a point** the GT's run bit can stay set; the next scan refuses ("another user") until the board is reprogrammed.
- **Changing `--eq`** pulses RXDFELPMRESET; the link can drop and relock briefly; the scan checks `link.ok_throughout`.
- The TX swing and cursor limits are enforced in the host (`hw.set_tx_drive`, the CLI and the owner script), not in the RTL: GT_DRIVE accepts any value.
- `--target-ber` deeper than 1e-10 runs for hours per full grid with the laser on; the script's scan list is bounded.
