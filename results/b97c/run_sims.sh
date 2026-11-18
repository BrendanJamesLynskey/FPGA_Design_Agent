#!/usr/bin/env bash
# Brief 97C: the core cocotb bench (rtl/b96_core.sv with the GT stand-in), 14 tests, for: the before state (origin/main RTL + the new tests, worktree 97c-base),
# and the three designs that are rebuilt: control (the base RTL), agent_both and all3 (the base with the variant's replaced files). Simulation only (Icarus).
#   results/b97c/run_sims.sh before|control|agent_both|all3
set -uo pipefail
W="${1:?before|control|agent_both|all3}"
R=/home/brendan/Claude_sandbox/_worktrees
case "$W" in before) ROOT=$R/97c-base;; *) ROOT=$R/97c-seq;; esac
OUT=$R/97c-seq/results/b97c
cd "$ROOT"
export FDA_SIM_BUILD_ROOT="$ROOT/build/sim_$W" B96_CORE_RESULTS="$OUT/core_sim_$W.json"
if [ "$W" = agent_both ] || [ "$W" = all3 ]; then
  export FDA_MUTANT_ORIG="$ROOT/designs/b96_kr260_10g/rtl" FDA_MUTANT_DIR="$ROOT/designs/b96_kr260_10g/lat_$W/rtl"
fi
systemd-run --user --scope -p MemoryMax=3G python3 -m pytest designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py -k core -q -p no:cacheprovider > "$OUT/pytest_$W.txt" 2>&1
cp "$FDA_SIM_BUILD_ROOT/b96_core/sim.log" "$OUT/sim_$W.log" 2>/dev/null
tail -3 "$OUT/pytest_$W.txt"
