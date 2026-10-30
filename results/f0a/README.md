# results/f0a

Build results for milestone F0A. Built with `flow/run_vivado.sh designs/t1_dimmer_counter both` in a fresh clone
of the branch at commit `98d2de3`, then collected with `flow/summarise.py`. Vivado 2025.2, local build PC.

| File | What |
|---|---|
| [t1_dimmer_counter.md](t1_dimmer_counter.md) | The summary table: gates, timing, utilisation, ILA cost, power, run time, memory |
| `t1_dimmer_counter_base.json`, `t1_dimmer_counter_ila.json` | Everything the table is made from: `gates` (flow/gates.py) and `run` (the runner's run.json) |
| `t1_dimmer_counter_ila_probe_map.txt` | Which signal is on which ILA probe port in the ILA build |
| `t1_dimmer_counter_rebuilds.json` | Every recorded build of the same sources (build stamp `dfd4624e`): three base builds from two commits and two clones, and two ILA builds, with identical timing and utilisation |
| `t1_dimmer_counter_ila_run_before_thread_pinning.json` | The ILA build before `synth.maxThreads` and `chipscope.maxJobs` were pinned to 1: peak anonymous memory 5946 MiB against the 6 GiB cap, cap reached 111 times (no OOM kill). After pinning: 4238 MiB, cap never reached |
