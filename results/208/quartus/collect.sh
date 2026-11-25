#!/bin/bash
# Brief 208: copy one Quartus arm's records into results/208/runs/quartus/<arm>/ (from the build root given)
Q=$1; shift
for n in "$@"; do
  D=$(dirname "$0")/../records/quartus/$n; mkdir -p "$D"
  cp "$Q/$n/$n.fit.summary" "$D/fit_summary.txt"
  grep -a -E "^ *(Warning|Critical Warning|Error)" "$Q/$n/compile.log" | sed -E 's/^ +//' | sort -u > "$D/messages.txt"
  grep -a -E "^ *(Warning|Critical Warning|Error)" "$Q/$n/sta.log" | sed -E 's/^ +//' | sort -u > "$D/sta_messages.txt"
  cp "$Q"/$n/sta_*.rpt "$D/"; cp "$Q/$n/mk.tcl" "$D/"
  L=$(grep -a -n "Compilation Hierarchy Node" "$Q/$n/$n.map.rpt" | head -1 | cut -d: -f1)
  sed -n "${L},$((L+12))p" "$Q/$n/$n.map.rpt" > "$D/map_entities.txt"
  grep -a -E "Version|Revision" "$Q/$n/$n.flow.rpt" | head -3 > "$D/version.txt"
done
