#!/usr/bin/env bash
# run_dumps.sh: after run_placements.sh, read each written checkpoint back (flow/managed_block_dump.tcl: the block's cells, BELs and routing
# in the saved file, and where every other cell sits), then re-run the comparison with those dumps. Needs the heavy slot of the caller.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$HERE/../.."
W="$HERE/build/pr"; R="$ROOT/results/102_managed_pr/placements"
for tag in $(python3 -c "import json,sys; print(' '.join(s['tag'] for s in json.load(open('$W/placements.json'))))"); do
  [ -f "$W/${tag}_dump.txt" ] || FDA_PR_DCP="$W/${tag}_routed.dcp" FDA_PR_CELL=u_blk FDA_PR_OUT="$W/${tag}_dump.txt" FDA_PR_NETS="$W/${tag}_routes_before.txt" \
    "$ROOT/designs/b100_rapidwright/scripts/viv.sh" "$ROOT/flow/managed_block_dump.tcl" "$W/${tag}_dump.log"
done
python3 "$ROOT/flow/managed_placed.py" compare "$HERE" "$W" --out "$R/placement_evidence.json" || true
