# results/19_ipgen_2026_1: the IP-generation worked examples on Vivado 2026.1 (brief 49)

Every example of [results/19_ipgen](../19_ipgen/README.md) re-run on **Vivado 2026.1** (Basic licence tier) on 2026-11-12 with
the same specs (`python3 -m flow.ipgen.run <adapter> results/19_ipgen_2026_1/<example>/spec.yaml results/19_ipgen_2026_1/<example>`;
`dds_no_margin` and `dds_coherent` with `--stages design,create,sim`, as before), and the chain model
(`python3 -m flow.ipgen.chain results/19_ipgen_2026_1/chain/chain.yaml results/19_ipgen_2026_1/chain`, no Vivado). The Vivado
work directory and the generated `*_cfg.tcl` are not committed; its stamped OOC reports are, as `ooc_utilization.rpt`,
`ooc_timing_path.rpt` and `ooc_timing_summary.rpt` beside each `ooc.json` (which carries no version and is byte-identical to the
earlier record where nothing moved). File meanings are as in the earlier folder's README.

Compared with the earlier release:

- **Simulations (xsim, word for word against the Python models): identical** for all seven examples; so are the chain results.
- **Out-of-context synthesis:** identical for `fir`, `chain_fir`, `cic` and `bmg_sine`; `dds` moved slightly: 120 LUT, WNS +7.045 ns,
  Fmax estimate 338.4 MHz (was 117 LUT, +7.105 ns, 345.4 MHz).
- **Read-back:** identical, except that 2026.1 reports a new `CONFIG.MEMORY_OPTIMIZATION` (true) on the Block Memory Generator, and the
  DDS read-back `C_PHASE_INCREMENT_VALUE` is the same value for `dds` and `dds_no_margin` (it differed on the earlier release) while
  their simulated outputs are unchanged. Not investigated further.

## Records

Each example directory (`fir`, `cic`, `chain_fir`, `bmg_sine`, `dds`, `dds_no_margin`, `dds_coherent`) holds `spec.yaml`,
`design.json`, `readback.json`, `sim.json`, `ooc.json`, the stamped `ooc_*.rpt` files and the IP data and stimulus files,
as described in the earlier folder's README; `chain/` holds `chain.yaml`, `chain.svg`, `chain_results.json` and
`output_spectrum.csv`.

## Reproduce

The commands are in the second paragraph: one `flow.ipgen.run` per example (Vivado 2026.1 and xsim, heavy slot) and
`flow.ipgen.chain` for the chain (Python only). `flow/ipgen/tests/test_19_results.py` recomputes the golden outputs from the committed stimulus and output files.

## Known gaps and limits

- Out-of-context synthesis is an upper bound on Fmax: no routing, no board.
- The new `CONFIG.MEMORY_OPTIMIZATION` read-back and the DDS `C_PHASE_INCREMENT_VALUE` change were not investigated.
- Only the DDS, FIR, CIC and Block Memory Generator adapters exist; the cascade was simulated stage by stage, not as one run.
- The chain figures come from a Python model of the chain, not from a board or a measured microphone.
- Supersedes `results/19_ipgen`.
