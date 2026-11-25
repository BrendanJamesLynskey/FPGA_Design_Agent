#!/usr/bin/env bash
# run_all.sh: every brief 207 measurement in order, one heavy job at a time (each script takes and releases its own slot).
#   run_all.sh <out dir>
set -u
here="$(cd "$(dirname "$0")" && pwd)"
out="$1"
"$here/run_quartus.sh" "$out" cv m10
for f in cv m10; do
  "$here/run_quartus_sta.sh" "$out" q_${f}_good_D_s1 DD
  "$here/run_quartus_sta.sh" "$out" q_${f}_good_N_s1 D
  "$here/run_quartus_sta.sh" "$out" q_${f}_good_U_s1 D
done
"$here/run_vivado.sh" "$out" xpm_a7 good_a7 b1_a7 b2_a7 b3_a7 xpm_k26 good_k26 b1_k26 b2_k26 b3_k26
