#!/usr/bin/env bash
# Brief 126: the core cocotb bench (Icarus, GT stand-in, the default receive path, tests/core_cocotb_default.py) with lat_all3's trade64.sv and tx_path.sv swapped in for the base's, as results/b97c/run_sims.sh does for all3,
# on the CURRENT tree (which has 96C, 96E, 96F1 and 96F1b below it). The bench cannot run the bypass core: Icarus has no model of xpm_cdc_async_rst (flow/cdc_models) and the stand-in transceiver has no
# bypass-controller ports; the bypass core's difference from the base core is checked by tests/test_b96f1_bypass.py::test_bypass_core_differs_from_base_only_where_documented and its behaviour by core_sim.sh (xsim, real XPM).
# The bench's testbench (sim/tb_core.sv) does not pass GO_REG, so this run has the go-pulse register ON (GO_REG = 1); the GO_REG = 0 build is covered by core_sim.sh, which reads the safety counters.
#   results/b126/run_cocotb.sh [control|all3]      simulation only (no heavy slot while load is under 6 and more than 12 GB is free)
set -uo pipefail
W="${1:-all3}"; ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; OUT="$ROOT/results/b126/cocotb"; mkdir -p "$OUT"; cd "$ROOT"
export FDA_SIM_BUILD_ROOT="$ROOT/build/sim126_$W" B96_CORE_RESULTS="$OUT/core_sim_$W.json"
if [ "$W" = all3 ]; then export FDA_MUTANT_ORIG="$ROOT/designs/b96_kr260_10g/rtl" FDA_MUTANT_DIR="$ROOT/designs/b96_kr260_10g/lat_all3/rtl"; fi
systemd-run --user --scope -p MemoryMax=3G python3 -m pytest designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py -k core_cocotb_default -q -p no:cacheprovider > "$OUT/pytest_$W.txt" 2>&1
cp "$FDA_SIM_BUILD_ROOT/b96_core_default/sim.log" "$OUT/sim_$W.log" 2>/dev/null
tail -3 "$OUT/pytest_$W.txt"
