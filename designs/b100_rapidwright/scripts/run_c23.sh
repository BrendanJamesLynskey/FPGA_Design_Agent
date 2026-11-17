#!/usr/bin/env bash
# run_c23.sh: capabilities 2 and 3 of brief 100 on the K26 transmit chain (rtl/chain_top.sv: brief 96's mac64_tx + pcs_tx and a bare GT).
# For each period perturbation (the "seed" of Vivado's placer, see docs/design.md section 4):
#   base   Vivado alone: synthesis (once), place, route.
#   place  RapidWright re-places the chain slices (a seed of its own), Vivado routes. Capability 2. placew: the same with the nets on Vivado's
#          worst paths weighted ten times in RapidWright's cost.
#   rwr    RWRoute routes the Vivado-placed design in full, no Vivado routing. Capability 3.
#   fixed  RWRoute re-routes the nets on Vivado's worst paths in Vivado's routed result and locks them, the other routes are kept. Capability 3.
# Every result is Vivado's (referee.tcl: route status, DRC, timing). Needs a heavy slot taken by the caller. Results: results/b100/c23/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
R="$ROOT/results/b100/c23"; D="$ROOT/designs/b100_rapidwright"; B96="$ROOT/designs/b96_kr260_10g/rtl"
export B100_PART=xck26-sfvc784-2LV-c B100_TOP=chain_top B100_XDC="$D/chain.xdc"
export B100_SRC="$B96/b96_pkg.sv $B96/pcs_tx.sv $B96/mac64_tx.sv $D/rtl/chain_top.sv"
BASE="${BASE:-3.40}"; STEPS="${STEPS:-0 1 2 3}"           # target period of seed 0 and the perturbation indexes (0.01 ns each)
mkdir -p "$R"
CHAIN="$R/chain.json"
echo '{"cells": ["u_pcs/*", "u_mac/*"], "anchor": "GTHE4_CHANNEL_X0Y6", "window": {"cols": 60, "rows": 40}}' > "$CHAIN"
for i in $STEPS; do
  P=$(python3 -c "print(f'{$BASE + 0.01*$i:.2f}')"); tag="s$i"
  # --- baseline: Vivado alone
  if [ ! -f "$R/base_${tag}_run.json" ]; then
    if [ -f "$R/synth.dcp" ]; then FROM="$R/synth.dcp"; else FROM=synth; fi
    B100_FROM=$FROM B100_PERIOD=$P B100_OUT="$R/base_$tag" "$HERE/viv.sh" "$HERE/impl.tcl" "$R/base_$tag.log"
    [ -f "$R/synth.dcp" ] || cp "$R/base_${tag}_synth.dcp" "$R/synth.dcp"
  fi
  # --- the nets on Vivado's worst paths (weights for placew, the nets RWRoute fixes in fixed)
  if [ ! -f "$R/crit_${tag}_nets.txt" ]; then
    B100_IN_DCP="$R/base_${tag}_routed.dcp" B100_OUT="$R/crit_${tag}_nets.txt" B100_PATHS=20 "$HERE/viv.sh" "$ROOT/flow/rw/critnets.tcl" "$R/crit_$tag.log"
    sed 's/$/ 10/' "$R/crit_${tag}_nets.txt" > "$R/crit_${tag}_weights.txt"
  fi
  # --- capability 2: RapidWright places the chain, Vivado routes and judges
  if [ ! -f "$R/place_${tag}_run.json" ]; then
    "$HERE/rw.sh" "$R/place_$tag.rw.log" "$ROOT/flow/rw/place_chain.py" "$R/base_${tag}_placed.dcp" "$R/place_${tag}_in.dcp" "$CHAIN" --seed $((i + 1)) --iters 200000
    B100_IN_DCP="$R/place_${tag}_in.dcp" B100_OUT="$R/place_$tag" B100_ROUTE=1 "$HERE/viv.sh" "$ROOT/flow/rw/referee.tcl" "$R/place_$tag.log"
  fi
  # --- capability 2 with Vivado's critical nets weighted ten times in RapidWright's cost
  if [ ! -f "$R/placew_${tag}_run.json" ]; then
    "$HERE/rw.sh" "$R/placew_$tag.rw.log" "$ROOT/flow/rw/place_chain.py" "$R/base_${tag}_placed.dcp" "$R/placew_${tag}_in.dcp" "$CHAIN" --seed $((i + 1)) --iters 200000 --crit "$R/crit_${tag}_weights.txt"
    B100_IN_DCP="$R/placew_${tag}_in.dcp" B100_OUT="$R/placew_$tag" B100_ROUTE=1 "$HERE/viv.sh" "$ROOT/flow/rw/referee.tcl" "$R/placew_$tag.log"
  fi
  # --- capability 3a: RWRoute routes everything
  if [ ! -f "$R/rwr_${tag}_run.json" ]; then
    "$HERE/rw.sh" "$R/rwr_$tag.rw.log" "$ROOT/flow/rw/route.py" full "$R/base_${tag}_placed.dcp" "$R/rwr_${tag}_in.dcp" timing
    B100_IN_DCP="$R/rwr_${tag}_in.dcp" B100_OUT="$R/rwr_$tag" B100_ROUTE=0 "$HERE/viv.sh" "$ROOT/flow/rw/referee.tcl" "$R/rwr_$tag.log"
  fi
  # --- capability 3b: RWRoute re-routes the nets on Vivado's worst paths in Vivado's own routed result; the other routes are kept
  #     (a first version fixed those nets on the placed, unrouted design and let Vivado route the rest: Vivado refused it, the fixed
  #     routes took wires other pins needed; results/b100/c23/first_pass_bugs/fixed_unlocked_partial/ and design.md section 6)
  if [ ! -f "$R/fixed_${tag}_run.json" ]; then
    "$HERE/rw.sh" "$R/fixed_$tag.rw.log" "$ROOT/flow/rw/route.py" nets "$R/base_${tag}_routed.dcp" "$R/fixed_${tag}_in.dcp" "$R/crit_${tag}_nets.txt"
    B100_IN_DCP="$R/fixed_${tag}_in.dcp" B100_OUT="$R/fixed_$tag" B100_ROUTE=0 "$HERE/viv.sh" "$ROOT/flow/rw/referee.tcl" "$R/fixed_$tag.log"
  fi
  rm -rf "$R"/*_in.dcp "$R"/*_in.dcp.edf "$R"/*.dcp.edf 2>/dev/null || true
done
