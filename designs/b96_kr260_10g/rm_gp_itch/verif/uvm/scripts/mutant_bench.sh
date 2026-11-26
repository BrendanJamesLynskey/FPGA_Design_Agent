#!/usr/bin/env bash
# mutant_bench.sh <build dir> <override dir>: build the ITCH/OUCH UVM bench against a directory of mutated RTL files and run the mutation test list until a test fails.
# Prints one last line: PASS (the mutant survived), FAIL (a test failed: killed) or INVALID (the mutated RTL does not build). Used by flow/mutation_b170.py (brief 170).
HERE="$(cd "$(dirname "$0")/.." && pwd)"
B="$1"; OVR="$2"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"; [ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +u; source "$SETTINGS" >/dev/null 2>&1
mkdir -p "$B"
ITCH_BOTH=0 "$HERE/scripts/uvm_build.sh" "$B" "$OVR" > "$B/build.txt" 2>&1 || { echo INVALID; exit 0; }
cd "$B"
for tt in ${MUT_TESTS:-t_smoke t_mold t_tail t_badfcs t_book t_risk t_hdr t_bp t_mix:1 t_rand:1 t_rand:2}; do
  t="${tt%%:*}"; s=1; case "$tt" in *:*) s="${tt##*:}";; esac
  xsim itch_uvm -runall -sv_seed "$s" -testplusarg "UVM_TESTNAME=$t" -testplusarg "SEED=$s" -testplusarg "ROUNDS=30" -log "run_${t}_$s.log" >/dev/null 2>&1
  if ! grep -aqE "\[RESULT\] PASS" "run_${t}_$s.log"; then echo "KILLED_BY $t seed $s"; echo FAIL; exit 0; fi
done
echo PASS
