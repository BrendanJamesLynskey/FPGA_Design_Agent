#!/usr/bin/env bash
# peak.sh <timefile> <command...>: run a command inside the current systemd scope and write its wall time and the scope's peak memory
# (cgroup memory.peak, all processes together, page cache included) to <timefile>. Used by viv.sh and rw.sh.
T="$1"; shift
CG="/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)"
S=$(date +%s.%N)
"$@"; rc=$?
E=$(date +%s.%N)
{ echo "wall_s $(echo "$E - $S" | bc)"; echo "peak_bytes $(cat "$CG/memory.peak" 2>/dev/null || echo unknown)"; echo "rc $rc"; } > "$T"
exit $rc
