# results/19_ipgen_2026_1: the IP-generation worked examples on Vivado 2026.1 (brief 49)

Every example of [results/19_ipgen](../19_ipgen/README.md) re-run on **Vivado 2026.1** (Basic licence tier) on 2026-11-12 with
the same specs (`python3 -m flow.ipgen.run <adapter> results/19_ipgen_2026_1/<example>/spec.yaml results/19_ipgen_2026_1/<example>`;
`dds_no_margin` and `dds_coherent` with `--stages design,create,sim`, as before), and the chain model
(`python3 -m flow.ipgen.chain results/19_ipgen_2026_1/chain/chain.yaml results/19_ipgen_2026_1/chain`, no Vivado). The Vivado
work directory and the generated `*_cfg.tcl` are not committed. File meanings are as in the earlier folder's README.

Compared with the earlier release:

- **Simulations (xsim, word for word against the Python models): identical** for all seven examples; so are the chain results.
- **Out-of-context synthesis:** identical for `fir`, `chain_fir`, `cic` and `bmg_sine`; `dds` moved slightly: 120 LUT, WNS +7.045 ns,
  Fmax estimate 338.4 MHz (was 117 LUT, +7.105 ns, 345.4 MHz).
- **Read-back:** identical, except that 2026.1 reports a new `CONFIG.MEMORY_OPTIMIZATION` (true) on the Block Memory Generator, and the
  DDS read-back `C_PHASE_INCREMENT_VALUE` is the same value for `dds` and `dds_no_margin` (it differed on the earlier release) while
  their simulated outputs are unchanged. Not investigated further.
