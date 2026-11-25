#!/usr/bin/env bash
# run_sim.sh: brief 207 functional and injected simulation of cdc207_top (Icarus; simulation only, no slot needed while load < 6 and
# > 12 GiB free). BAD=0 (good) and BAD=1 (binary pointers) and BAD=2 (one-stage synchroniser), each plain and with 5 injection seeds
# (flow/cdc_inject.py: each first-stage bit may take one extra destination cycle). Writes <out>/sim_results.txt.
#   run_sim.sh <out dir>
set -u
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../../../.." && pwd)"
out="$1"; mkdir -p "$out"; w=$(mktemp -d); trap 'rm -r "$w"' EXIT
: > "$out/sim_results.txt"
for b in 0 1 2; do for s in none 1 2 3 4 5; do
  d="$w/b${b}_$s"; mkdir -p "$d"
  plus=$(cd "$root" && python3 -c "
from flow import cdc_inject as C; from pathlib import Path
src,p,r=C.prepare([Path('$here/rtl/cdc207_top.v')],Path('$d'),None if '$s'=='none' else int('$s'))
open('$d/srcs','w').write(' '.join(str(x) for x in src)); print(' '.join(p))")
  iverilog -g2012 -DBADV=$b -o "$d/sim" -s tb_cdc207 "$here/rtl/tb_cdc207.v" $(cat "$d/srcs") || { echo "BAD=$b seed=$s BUILD-FAIL" >> "$out/sim_results.txt"; continue; }
  r=$(timeout 300 vvp -n "$d/sim" $plus | grep -E '^(PASS|FAIL|FIFO|POINTER|HS|CFG|PULSE|RESET)' | head -6 | tr '\n' ' ')
  echo "BAD=$b seed=$s $r" >> "$out/sim_results.txt"
done; done
cat "$out/sim_results.txt"
