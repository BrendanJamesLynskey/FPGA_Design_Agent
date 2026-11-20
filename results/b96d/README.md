# results/b96d: on-chip RX eye scan of the 10G link (brief 96D)

This folder holds the records of brief 96D: the Vivado build of the eye-scan variant, the simulation results of its sequencer, the offline (synthetic) example captures that exercise the host software and the displays, and, after the owner's
board session, the real eye captures under `hw/`. **Nothing under `offline/` is a measurement**: those files come from an invented statistical eye (`flow/eyescan/fake.py`), carry `synthetic: true` and a SYNTHETIC watermark, and exist to test
the software and to show what the displays look like.

## Records
- `builds/eyescan/`: `digest.json` (timing, utilisation, power, gates), `run.json` (memory and wall time), `wall.txt`, `run_vivado.log`, `commit.txt`, for the `designs/b96_kr260_10g/eyescan` build (`EYESCAN = 1`, `RATE_MATCH = 0`, `es.xdc`).
- `offline/lpm_synthetic.json`, `offline/dfe_synthetic.json`: two synthetic captures (fda-capture-eye/1) from the fake board, LPM and DFE; `offline/lpm_synthetic_eye.svg`, `offline/lpm_synthetic_bathtub.svg`: the static figures; `offline/eye_page_synthetic.html`: the interactive page with the Compare tab.
- `es_sim.txt`: the output of `tests/eyescan_cocotb.py` (the sequencer against the Python twin) and the default-off test.
- `hw/<stamp>/`: written by `_handoff/fpga_agent/run_96d_stage3.sh` when the owner runs it (probe, one capture per scan, `summary.txt`, `svg/`, `page.html`). `hw/20261119_231836/` is the first board run: **it counted no samples and measured no eye** (a driver fault, fixed in brief 96D2); see `hw/README.md`.

## Measured
Build, simulation and software tests only; see the report. No eye has been measured yet: the first board run (`hw/`) counted no samples at any point (see `hw/README.md`).

The `eyescan` build (clean tree at commit `c5cce52a`, Vivado 2026.1, `FDA_VIVADO_THREADS=1`, 1208 s): all 29 gates true; DRC and methodology critical warnings 0 (15 methodology warnings: LUTAR-1 x5, XDCH-2 x10); CDC critical 0; **WNS +0.095 ns, WHS +0.010 ns** (6.206 ns period); 6,350 LUT, 14,545 FF, 0 BRAM, 0 DSP; 1.081 W total, junction 48 C (`builds/eyescan/digest.json`, `run.json`). `attributes_in_post_route_dcp.txt` was read from the earlier build of the same `es.xdc` (ES_EYE_SCAN_EN and ES_ERRDET_EN TRUE) and not re-read on this one.

- `ibert_probe_results.txt`: the IBERT GTH licence probe (Vivado 2026.1, Basic): refused at top synthesis with `Chipscope 16-620` (a licence refusal, not a wrapper error; the first run's wrapper error was fixed and rerun).

## Reproduce
`python3 -m pytest designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py -k eyescan flow/tests/test_eyescan.py agent/tests/test_96d_eye_tool.py`; offline demo: `python3 -m flow.eyescan run --fake --out /tmp/eye --name demo` then `python3 -m flow.eyescan page /tmp/eye/demo.json -o /tmp/eye/page.html`;
board: `bash _handoff/fpga_agent/run_96d_stage3.sh <loop lead metres> YES` (owner).

## Known gaps and limits
No real eye has been scanned: the DRP map, the 32-bit reading of bits per sample and the masks are from UG576 and untested on the part. The `offline/` files are synthetic. The default build was not rebuilt or re-proved for this brief.
