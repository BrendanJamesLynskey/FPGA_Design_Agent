#!/usr/bin/env bash
# run_c1.sh: capability 1 of brief 100 end to end (needs a heavy slot taken by the caller, RapidWright installed, Vivado 2026.1).
#   1. implement pcs_unit out of context in a pblock (the block: rtl/pcs_unit.sv),
#   2. relocate it with RapidWright to three more sites,
#   3. stamp the four blocks into reloc_top (Vivado places the rest and routes the connections) at three period perturbations,
#   4. the same top with Vivado alone, a pblock at each site (the block's pblock moved by the same offset), at the same perturbations.
# Results in results/b100/c1/. Re-running skips finished steps.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
R="$ROOT/results/b100/c1"; D="$ROOT/designs/b100_rapidwright/rtl"; B96="$ROOT/designs/b96_kr260_10g/rtl"
export B100_PART=xck26-sfvc784-2LV-c
PERIODS="${PERIODS:-3.40 3.41 3.42}"
PB0="SLICE_X26Y70:SLICE_X37Y89"
TARGETS="SLICE_X35Y57 SLICE_X41Y117 SLICE_X41Y177"
mkdir -p "$R"
if [ ! -f "$R/blk_p0_ooc.dcp" ]; then
  B100_SRC="$B96/b96_pkg.sv $B96/pcs_tx.sv $D/pcs_unit.sv" B100_TOP=pcs_unit B100_PERIOD=3.4 B100_PBLOCK=$PB0 B100_OUT="$R/blk_p0" \
    "$HERE/viv.sh" "$HERE/ooc.tcl" "$R/blk_p0.log"
fi
for t in $TARGETS; do
  [ -f "$R/blk_$t.dcp" ] || "$HERE/rw.sh" "$R/rw_mv_$t.log" "$ROOT/flow/rw/relocate.py" moveto "$R/blk_p0_ooc.dcp" "$R/blk_$t.dcp" "$t"
done
# the Vivado-alone pblocks: the block's pblock shifted by the offset of each relocation (its anchor slice to the target slice)
PBLOCKS=$(python3 - "$PB0" "$R" $TARGETS <<'PY'
import json, re, sys
pb, R, targets = sys.argv[1], sys.argv[2], sys.argv[3:]
xy = lambda s: tuple(int(v) for v in re.match(r"SLICE_X(\d+)Y(\d+)", s).groups())
(x0, y0), (x1, y1) = (xy(p) for p in pb.split(":"))
out = [pb]
for t in targets:
    r = json.loads([l for l in open(f"{R}/rw_mv_{t}.log") if l.startswith("{")][-1])
    ax, ay = xy(r["anchor_before"]); tx, ty = xy(t)
    out.append(f"SLICE_X{x0+tx-ax}Y{y0+ty-ay}:SLICE_X{x1+tx-ax}Y{y1+ty-ay}")
print(" ".join(out))
PY
)
echo "pblocks: $PBLOCKS" | tee "$R/pblocks.txt"
BLOCKS="$R/blk_p0_ooc.dcp $(for t in $TARGETS; do printf '%s ' "$R/blk_$t.dcp"; done)"
for P in $PERIODS; do
  tag="p${P/./_}"
  for arm in stamp alone; do
    if [ ! -f "$R/${arm}_${tag}_routed.dcp" ]; then
      if [ $arm = stamp ]; then
        B100_MODE=stamp B100_PERIOD=$P B100_SRC="$D/reloc_top.sv $D/pcs_unit_bb.sv" B100_OUT="$R/stamp_$tag" B100_BLOCKS="$BLOCKS" \
          "$HERE/viv.sh" "$HERE/stamp.tcl" "$R/stamp_$tag.log"
      else
        B100_MODE=alone B100_PERIOD=$P B100_SRC="$D/reloc_top.sv $B96/b96_pkg.sv $B96/pcs_tx.sv $D/pcs_unit.sv" B100_OUT="$R/alone_$tag" \
          B100_PBLOCKS="$PBLOCKS" "$HERE/viv.sh" "$HERE/stamp.tcl" "$R/alone_$tag.log"
      fi
    fi
    # the block-internal paths, read from the routed checkpoint (Vivado's timing; no further routing)
    [ -s "$R/${arm}_${tag}_blocks.csv" ] && [ "$(wc -l < "$R/${arm}_${tag}_blocks.csv")" -gt 10 ] || \
      B100_IN_DCP="$R/${arm}_${tag}_routed.dcp" B100_OUT="$R/${arm}_${tag}" B100_ROUTE=0 "$HERE/viv.sh" "$HERE/stamp_referee.tcl" "$R/${arm}_${tag}.referee.log"
  done
done
python3 "$HERE/analyse_blocks.py" "$R/summary.json" $(for P in $PERIODS; do tag="p${P/./_}"; echo "stamp_$tag=$R/stamp_${tag}_blocks.csv alone_$tag=$R/alone_${tag}_blocks.csv"; done)
