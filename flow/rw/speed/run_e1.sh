#!/usr/bin/env bash
# run_e1.sh: brief 100B experiment 1 (the build after a one-block edit), three repetitions of every arm, arms interleaved so that file-cache
# and thermal state do not favour one. Needs the heavy slot, Vivado 2026.1, the RapidWright venv and the input checkpoints in $W/in
# (the blocks and the reference placement of brief 100's c1 run). Resumable: a finished step (its .meas.json) is skipped.
#   F  Vivado alone from RTL (full rebuild)     I  Vivado alone with read_checkpoint -incremental of the unedited design's routed checkpoint
#   S  stitch: edited block implemented out of context in its pblock, then stamped with the three cached blocks (Vivado places the rest and routes)
#   S2 the stamp's placed checkpoint routed with RWRoute (complete mode, soft preserve), Vivado's timing as referee (no Vivado route)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
W="${W:-/home/brendan/Claude_sandbox/_worktrees/100b-work}"; OUT="$W/e1"; IN="$W/in"
RTL="$ROOT/designs/b100_rapidwright/rtl"; B96="$ROOT/designs/b96_kr260_10g/rtl"
export B100_PART=xck26-sfvc784-2LV-c B100_PERIOD=3.4 B100_THREADS=1
PBLOCKS="SLICE_X26Y70:SLICE_X37Y89 SLICE_X26Y40:SLICE_X37Y59 SLICE_X32Y100:SLICE_X43Y119 SLICE_X32Y160:SLICE_X43Y179"
REPS="${REPS:-1 2 3}"
step() { local tag="$1"; shift; [ -f "$OUT/$tag.meas.json" ] && return 0; "$HERE/meas.sh" "$tag" "$OUT" "$@" || echo "step $tag failed rc=$?" | tee -a "$OUT/failures.txt"; }
mkdir -p "$OUT"
for r in $REPS; do
  # F: full rebuild
  B100_MODE=full B100_SRC="$RTL/reloc_top_edit.sv $B96/b96_pkg.sv $B96/pcs_tx.sv $RTL/pcs_unit.sv $RTL/pcs_unit_e.sv" B100_PBLOCKS="$PBLOCKS" B100_OUT="$OUT/F$r.d/res" \
    step F$r vivado "$HERE/e1.tcl"
  # I: Vivado incremental
  B100_MODE=incr B100_REF="$IN/alone_p3_40_routed.dcp" B100_SRC="$RTL/reloc_top_edit.sv $B96/b96_pkg.sv $B96/pcs_tx.sv $RTL/pcs_unit.sv $RTL/pcs_unit_e.sv" \
    B100_PBLOCKS="$PBLOCKS" B100_OUT="$OUT/I$r.d/res" step I$r vivado "$HERE/e1.tcl"
  # S: the edited block out of context, then the stamp
  B100_SRC="$B96/b96_pkg.sv $B96/pcs_tx.sv $RTL/pcs_unit_e.sv" B100_TOP=pcs_unit_e B100_PERIOD=3.4 B100_PBLOCK=SLICE_X32Y100:SLICE_X43Y119 B100_OUT="$OUT/Sblk$r.d/blk" \
    step Sblk$r vivado "$ROOT/designs/b100_rapidwright/scripts/ooc.tcl"
  B100_MODE=stamp B100_SRC="$RTL/reloc_top_edit.sv $RTL/pcs_unit_bb.sv $RTL/pcs_unit_e_bb.sv" \
    B100_BLOCKS="$IN/blk_p0_ooc.dcp $IN/blk_SLICE_X35Y57.dcp $OUT/Sblk$r.d/blk_ooc.dcp $IN/blk_SLICE_X41Y177.dcp" B100_OUT="$OUT/Sstamp$r.d/res" \
    step Sstamp$r vivado "$HERE/e1.tcl"
  # S2: RWRoute completion of the stamp's placed checkpoint, then Vivado's timing
  [ -f "$OUT/Sstamp$r.d/res_placed.dcp" ] && {
    step S2rw$r rw "$ROOT/flow/rw/route.py" complete "$OUT/Sstamp$r.d/res_placed.dcp" "$OUT/S2rw$r.d/res_routed.dcp"
    [ -f "$OUT/S2rw$r.d/res_routed.dcp" ] && B100_IN_DCP="$OUT/S2rw$r.d/res_routed.dcp" B100_OUT="$OUT/S2ref$r.d/res" step S2ref$r vivado "$HERE/referee.tcl"
  }
done
echo "run_e1 done" >> "$OUT/failures.txt"
