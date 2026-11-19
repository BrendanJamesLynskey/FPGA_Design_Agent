#!/usr/bin/env bash
# run_placements.sh: the placement evidence of brief 102, stage 2. For each placement of the locked block (delivered, relocated by RapidWright
# to three other sites, and delivered again with another placer directive) Vivado places and routes the owned logic around it, and the facts
# that say whether the block was left alone and how it times are written (flow/managed_placement_run.tcl); flow/managed_block_dump.tcl (run_dumps.sh)
# reads each written checkpoint back and fingerprints the block's logical netlist; flow/managed_placed.py compare writes the evidence.
# Needs a heavy slot taken by the caller (Vivado 2026.1 one thread, RapidWright installed: tools/rapidwright_env/setup.sh), Re-running skips finished steps. Work files are in the design's git-ignored build/pr/; records go to results/102_managed_pr/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$HERE/../.."
W="$HERE/build/pr"; R="$ROOT/results/102_managed_pr/placements"; mkdir -p "$W" "$R"
B100="$ROOT/designs/b100_rapidwright/scripts"
export FDA_PR_PART=xck26-sfvc784-2LV-c FDA_PR_TOP=pr_top FDA_PR_CELL=u_blk FDA_PR_THREADS=1
export FDA_PR_SRC="$HERE/ext/pcs_unit_bb.sv $HERE/rtl/pr_src.sv $HERE/rtl/pr_sink.sv $HERE/rtl/pr_top.sv" FDA_PR_XDC="$HERE/design.xdc"
VIV="$ROOT/flow/managed_placement_run.tcl"
# tag:target site:directive[:extra xdc] ('-' = the delivered placement; the extra xdc is the agent's own constraints for that arm)
PLACEMENTS="${PLACEMENTS:-p0:-:Default p0x:-:Explore p0y:-:Default:$HERE/scripts/sink_pblock.xdc p1:SLICE_X29Y20:Default p2:SLICE_X29Y50:Default p3:SLICE_X5Y170:Default}"
python3 "$ROOT/flow/managed_import.py" budget-tcl "$HERE" - "$W/budget.tcl" >/dev/null
spec="["
for item in $PLACEMENTS; do
  IFS=: read -r tag site dir xdc <<<"$item"
  dcp="$HERE/ext/pcs_unit_p0.dcp"
  if [ "$tag" = p0 ] && [ ! -f "$W/p0_funcsim.v" ]; then
    FDA_PR_DCP="$dcp" FDA_PR_OUT="$W/p0_facts.txt" FDA_PR_FUNCSIM="$W/p0_funcsim.v" "$B100/viv.sh" "$ROOT/flow/managed_placed_check.tcl" "$W/p0_check.log"
  fi
  if [ "$site" != "-" ]; then
    dcp="$W/blk_$tag.dcp"
    [ -f "$dcp" ] || "$B100/rw.sh" "$W/rw_$tag.log" "$ROOT/flow/rw/relocate.py" moveto "$HERE/ext/pcs_unit_p0.dcp" "$dcp" "$site"
    # the relocated block's functional netlist, for eqy against the delivered one
    [ -f "$W/${tag}_funcsim.v" ] || FDA_PR_DCP="$dcp" FDA_PR_OUT="$W/${tag}_facts.txt" FDA_PR_FUNCSIM="$W/${tag}_funcsim.v" \
      "$B100/viv.sh" "$ROOT/flow/managed_placed_check.tcl" "$W/${tag}_check.log"
  fi
  if [ ! -f "$W/${tag}_run.json" ]; then
    FDA_PR_DCP="$dcp" FDA_PR_OUT="$W/$tag" FDA_PR_DIRECTIVE="$dir" FDA_PR_EXTRA_XDC="${xdc:-}" FDA_PR_BUDGET_TCL="$W/budget.tcl" \
      "$B100/viv.sh" "$VIV" "$W/$tag.log"
  fi
  note="relocated to $site"; [ "$site" = "-" ] && note="delivered placement, placer directive $dir${xdc:+, the sink held in a pblock beside the block (scripts/sink_pblock.xdc)}"; [ "$tag" = p0 ] && note="delivered placement"
  spec="$spec{\"tag\": \"$tag\", \"prefix\": \"$tag\", \"note\": \"$note\"},"
done
echo "${spec%,}]" > "$W/placements.json"
# the delivered placement's own funcsim is needed by the relocated ones' eqy: written once, from the delivered checkpoint
python3 "$ROOT/flow/managed_placed.py" compare "$HERE" "$W" --out "$R/placement_evidence.json" || true
for f in "$W"/*_run.json "$W"/*_block.csv; do cp "$f" "$R/"; done
for t in $PLACEMENTS; do tag="${t%%:*}"; grep '^BUDGET|' "$W/$tag.log" > "$R/${tag}_budgets.txt" || true; done
