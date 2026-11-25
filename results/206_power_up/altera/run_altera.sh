#!/bin/bash
# Brief 206: compile the Altera power-up arms (Quartus Prime Lite 25.1std), one case at a time, under the heavy slot the
# caller took. Usage: run_altera.sh <build-dir> [case ...]   case = <tag>:<INITV>:<pushback>, default all nine below.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
b=${1:?build dir}; shift; mkdir -p "$b"
cases=${*:-"c4:0:ON c4:1:ON c4:1:OFF m10:0:ON m10:1:ON m10:1:OFF c5:0:ON c5:1:ON c5:1:OFF"}
QS=/home/brendan/altera_lite/25.1std/quartus/bin/quartus_sh
for c in $cases; do
  IFS=: read -r tag initv pb <<< "$c"
  echo "== $c $(date '+%H:%M:%S')"
  systemd-run --user --scope --unit="fda206-q-$tag-$initv-$pb" -p MemoryMax=3G nice -n 15 \
    "$QS" -t "$here/tcl/q_project.tcl" "$tag" "$initv" "$pb" "$b" "$here/rtl" "$here/../amd/rtl" > "$b/q_${tag}_i${initv}_pb${pb}.out" 2>&1 || echo "rc=$? for $c"
done
