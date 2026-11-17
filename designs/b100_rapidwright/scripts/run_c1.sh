#!/usr/bin/env bash
# run_c1.sh: capability 1 of brief 100 end to end (needs a heavy slot taken by the caller, RapidWright installed, Vivado 2026.1).
#   1. implement pcs_tx out of context in a pblock (the block), 2. relocate it with RapidWright to three more sites,
#   3. stamp the four blocks into reloc_top (Vivado places the rest and routes the connections) at three period perturbations,
#   4. the same top with Vivado alone, a pblock at each site, at the same three perturbations. Results in results/b100/c1/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
R="$ROOT/results/b100/c1"; D="$ROOT/designs/b100_rapidwright/rtl"; B96="$ROOT/designs/b96_kr260_10g/rtl"
export B100_PART=xck26-sfvc784-2LV-c
PERIODS="${PERIODS:-3.40 3.41 3.42}"
PB0="SLICE_X26Y70:SLICE_X37Y89"          # the block's pblock; its anchor slice is SLICE_X29Y80
declare -A TARGET=([B]=SLICE_X29Y110 [C]=SLICE_X38Y60 [D]=SLICE_X38Y140)
declare -A PBLOCK=([A]=$PB0 [B]="SLICE_X26Y100:SLICE_X37Y119" [C]="SLICE_X35Y50:SLICE_X46Y69" [D]="SLICE_X35Y130:SLICE_X46Y149")
mkdir -p "$R"
if [ ! -f "$R/blk_p0_ooc.dcp" ]; then
  B100_SRC="$B96/b96_pkg.sv $B96/pcs_tx.sv" B100_TOP=pcs_tx B100_PERIOD=3.4 B100_PBLOCK=$PB0 B100_OUT="$R/blk_p0" \
    "$HERE/viv.sh" "$HERE/ooc.tcl" "$R/blk_p0.log"
fi
for k in B C D; do
  [ -f "$R/blk_${TARGET[$k]}.dcp" ] || "$HERE/rw.sh" "$R/rw_mv_${TARGET[$k]}.log" "$ROOT/flow/rw/relocate.py" moveto "$R/blk_p0_ooc.dcp" "$R/blk_${TARGET[$k]}.dcp" "${TARGET[$k]}"
done
for P in $PERIODS; do
  tag="p${P/./_}"
  [ -f "$R/stamp_${tag}_blocks.csv" ] || B100_MODE=stamp B100_PERIOD=$P B100_SRC="$D/reloc_top.sv $D/pcs_tx_bb.sv" B100_OUT="$R/stamp_$tag" \
    B100_BLOCKS="$R/blk_p0_ooc.dcp $R/blk_${TARGET[B]}.dcp $R/blk_${TARGET[C]}.dcp $R/blk_${TARGET[D]}.dcp" "$HERE/viv.sh" "$HERE/stamp.tcl" "$R/stamp_$tag.log"
  [ -f "$R/alone_${tag}_blocks.csv" ] || B100_MODE=alone B100_PERIOD=$P B100_SRC="$D/reloc_top.sv $B96/b96_pkg.sv $B96/pcs_tx.sv" B100_OUT="$R/alone_$tag" \
    B100_PBLOCKS="${PBLOCK[A]} ${PBLOCK[B]} ${PBLOCK[C]} ${PBLOCK[D]}" "$HERE/viv.sh" "$HERE/stamp.tcl" "$R/alone_$tag.log"
done
python3 "$HERE/analyse_blocks.py" "$R/summary.json" $(for P in $PERIODS; do tag="p${P/./_}"; echo "stamp_$tag=$R/stamp_${tag}_blocks.csv alone_$tag=$R/alone_${tag}_blocks.csv"; done)
