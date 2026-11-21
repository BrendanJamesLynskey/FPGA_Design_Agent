#!/usr/bin/env bash
# time_xsim.sh: wall time of brief 112's SystemVerilog UVM bench in xsim, for the comparison with this bench (brief 123).
#   scripts/time_xsim.sh <out dir>      writes <out dir>/xsim_timing.tsv: the build time, then every run of 112's regression shape (11 directed tests x 2 seeds,
#                                        t_rand and t_rand_line x 10 seeds): wall seconds, simulated ns, PASS or FAIL
# Same machine rule as 112's regression: waits while the 1-minute load is 6 or more or less than 12 GB is free (the wait is not counted).
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; UVM="$HERE/../uvm"
OUT="$(mkdir -p "$1" && cd "$1" && pwd)"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"; [ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +u; source "$SETTINGS" >/dev/null 2>&1; set -u
wait_for_machine() { for _ in $(seq 90); do l=$(cut -d' ' -f1 /proc/loadavg); a=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
  awk -v l="$l" -v a="$a" 'BEGIN{exit !(l < 6 && a > 12)}' && return 0; sleep 20; done; echo "machine busy"; exit 3; }
now() { date +%s.%N; }
wait_for_machine
t0=$(now); "$UVM/scripts/uvm_build.sh" "$OUT/build" > "$OUT/build.txt" 2>&1 || { echo BUILD FAILED; exit 1; }; t1=$(now)
printf "item\twall_s\tsim_ns\n" > "$OUT/xsim_timing.tsv"
printf "build\t%.1f\t-\n" "$(echo "$t1 - $t0" | bc)" >> "$OUT/xsim_timing.tsv"
RUNS=""
for t in t_smoke t_lens t_gaps t_badfcs t_xg t_line_blocks t_hdr t_slip t_ber t_rxreset t_offsets; do RUNS="$RUNS $t:1 $t:2"; done
for t in t_rand t_rand_line; do for s in $(seq 10); do RUNS="$RUNS $t:$s"; done; done
for r in $RUNS; do
  t="${r%%:*}"; SEED="${r##*:}"
  wait_for_machine
  mkdir -p "$OUT/runs/${t}_$SEED"; log="$OUT/runs/${t}_$SEED/run.log"
  a=$(now)
  ( cd "$OUT/build" && xsim pcs_uvm -runall -sv_seed "$SEED" -testplusarg "UVM_TESTNAME=$t" -testplusarg "SEED=$SEED" -log "$log" >/dev/null 2>&1 )
  b=$(now)
  ns=$(grep -aoE '\$finish called at time : [0-9.]+ ?[a-z]+' "$log" | tail -1 | sed -E 's/.*: ([0-9.]+) ?([a-z]+)/\1 \2/' | awk '{u=$2; v=$1; if(u=="us")v*=1000; else if(u=="ms")v*=1e6; else if(u=="ps")v/=1000; printf "%.0f", v}')
  res=$(grep -aE "\[RESULT\] (PASS|FAIL)" "$log" | tail -1 | grep -aoE "PASS|FAIL")
  printf "%s_%s\t%.1f\t%s\t%s\n" "$t" "$SEED" "$(echo "$b - $a" | bc)" "${ns:--}" "${res:--}" >> "$OUT/xsim_timing.tsv"
done
cat "$OUT/xsim_timing.tsv"
