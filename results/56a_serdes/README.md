# results/56a_serdes: the transceiver build, licence and probe records (brief 56A)

Records from brief 56A on the Kria KR260's K26 part (`xck26-sfvc784-2LV-c`), Vivado 2026.1 on the free Basic licence: the GT pin and site map, one GT design built to a bitstream
with its flow gates, a licence and build probe of the transceiver-related AMD IP, the Vivado Simulator's refusal of the GT Wizard model, and the register-level bench result against
a stand-in. Nothing here was run on a board. The design is [designs/b56a_gth_serdes](../../designs/b56a_gth_serdes/README.md).

## Records

| File | What it is |
|---|---|
| `gt_sites.txt`, `gt_sites.json` | package pins, functions and GT sites of the part (quad 224 = `GTHE4_CHANNEL_X0Y4` to `X0Y7`; the SFP+ lane is `X0Y6`); the JSON is `flow/gt_parts/xck26.json` |
| `build/run.json`, `build/gates.json`, `build/manifest.json` | the b56a design's build: time, memory peaks, every flow and GT gate, build ID |
| `build/utilization.rpt`, `build/timing_summary.rpt`, `build/power.rpt`, `build/tool.txt`, `build/stages.txt` | the build's Vivado reports and stage times |
| `licences.md` | the licence table with exact error texts, per IP and stage |
| `probe/probe_results.json` | the RESULT lines of each probe (stage, status, text, peak memory) |
| `xsim_refusal.txt`, `xxv_licence_refusal.txt` | the exact refusal texts of the simulator and of `xxv_ethernet` |
| `core_sim_standin.txt` | the register-level bench against the behavioural stand-in of the Wizard (23 checks) |

## Measured

- Build of `designs/b56a_gth_serdes` (one run, 2 threads, `MemoryMax=8G`, nothing else running): 341.7 s wall; **Vivado peak resident memory 4235 MiB, the scope's anonymous peak 3538 MiB**, no cap hits (`build/run.json`). The first GT build alone, as the brief asked.
- Timing at the 161.133 MHz user clocks and the 100 MHz clock: WNS 2.156 ns, WHS 0.016 ns, 0 failing endpoints; 973 LUTs, 3106 registers, 0 BRAM, 0 DSP; total on-chip power 0.764 W, vectorless, confidence Medium (`build/gates.json`).
- The free Vivado Simulator refuses the Wizard model: 54716 instances against a limit of 50000 (`xsim_refusal.txt`).
- `xxv_ethernet` is refused at synthesis; the Wizard builds to a bitstream (`licences.md`).

## Reproduce

Each record comes from the command beside it; the builds and probes are heavy Vivado jobs that need a heavy slot, and nothing needs hardware.

```
flow/run_vivado.sh designs/b56a_gth_serdes base          # heavy slot, Vivado 2026.1, about 6 minutes, ~4 GB
designs/b56a_gth_serdes/probe/run_probe.sh <ip> ...       # heavy slot; one Vivado per IP (names in probe/ip_probe.tcl)
vivado -mode batch -source designs/b56a_gth_serdes/probe/gt_sites.tcl
python3 -m pytest designs/b56a_gth_serdes/tests          # needs Icarus; B56A_RECORD=results/56a_serdes writes core_sim_standin.txt
```

## Known gaps and limits

- No board run; the reference clock source and frequency, the 25 MHz input and the SFP+ control pin functions are unconfirmed (open-source example, not the schematic).
- Implementation and bitstream of IP other than the Wizard were not established: IP used as a top has no pins and failed in placement, routing or a pin DRC for probe reasons (`licences.md`). `xdma` synthesis was cut short (unknown). The IBERT routable wrapper was written, not run.
- The register-level bench uses a stand-in, not the transceiver model; it shows the fabric, not the GT.
- One build, one run of each probe; memory figures are from the Vivado process on this machine at 2 threads.
- Raw Vivado logs are not committed (they are large); the RESULT lines and texts are.
