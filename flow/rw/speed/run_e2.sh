#!/usr/bin/env bash
# run_e2.sh <label> <placed.dcp> <period list>: brief 100B experiment 2, the router. One Vivado placement, restated at each period, routed by
#   V   Vivado route_design              RT  RWRoute full, timing-driven     RN  RWRoute full, not timing-driven
# three repetitions each, arms interleaved. Vivado's report_timing on every result is the referee (referee.tcl, not part of RWRoute's time).
# Needs the heavy slot. Resumable.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
W="${W:-/home/brendan/Claude_sandbox/_worktrees/100b-work}"
LABEL="$1"; PLACED="$2"; shift 2; PERIODS="$*"
OUT="$W/e2_$LABEL"; mkdir -p "$OUT"
export B100_THREADS=1
step() { local tag="$1"; shift; [ -f "$OUT/$tag.meas.json" ] && return 0; "$HERE/meas.sh" "$tag" "$OUT" "$@" || echo "step $tag failed rc=$?" | tee -a "$OUT/failures.txt"; }
for p in $PERIODS; do
  t="p${p/./_}"
  [ -f "$OUT/$t.dcp" ] || B100_IN_DCP="$PLACED" B100_OUT_DCP="$OUT/$t.dcp" B100_PERIOD=$p "$HERE/meas.sh" prep_$t "$OUT" vivado "$HERE/retime.tcl"
done
for r in 1 2 3; do for p in $PERIODS; do
  t="p${p/./_}"
  B100_IN_DCP="$OUT/$t.dcp" B100_OUT="$OUT/V_${t}_$r.d/res" B100_PERIOD=$p step V_${t}_$r vivado "$HERE/route_v.tcl"
  step RT_${t}_$r rw "$ROOT/flow/rw/route.py" full "$OUT/$t.dcp" "$OUT/RT_${t}_$r.d/res_routed.dcp" timing
  [ -f "$OUT/RT_${t}_$r.d/res_routed.dcp" ] && B100_IN_DCP="$OUT/RT_${t}_$r.d/res_routed.dcp" B100_OUT="$OUT/RTref_${t}_$r.d/res" B100_PERIOD=$p step RTref_${t}_$r vivado "$HERE/referee.tcl"
  step RN_${t}_$r rw "$ROOT/flow/rw/route.py" full "$OUT/$t.dcp" "$OUT/RN_${t}_$r.d/res_routed.dcp" nontiming
  [ -f "$OUT/RN_${t}_$r.d/res_routed.dcp" ] && B100_IN_DCP="$OUT/RN_${t}_$r.d/res_routed.dcp" B100_OUT="$OUT/RNref_${t}_$r.d/res" B100_PERIOD=$p step RNref_${t}_$r vivado "$HERE/referee.tcl"
done; done
echo "run_e2 $LABEL done" >> "$OUT/failures.txt"
