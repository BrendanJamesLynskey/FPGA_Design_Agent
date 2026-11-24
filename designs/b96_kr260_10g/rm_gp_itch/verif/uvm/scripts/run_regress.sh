#!/usr/bin/env bash
# run_regress.sh: the one-command regression of the ITCH/OUCH UVM bench (brief 170): build, run every test over its seeds, merge the coverage, optionally run the mutation sweep.
#   scripts/run_regress.sh [--out DIR] [--seeds N] [--rand N] [--rounds N] [--quick] [--record DIR] [--skip-build]
#     --out DIR      where builds, logs and reports go (default verif/uvm/build, git-ignored)
#     --seeds N      seeds per directed test (default 2); --rand N seeds for each constrained-random test (default 10); --rounds N: packets per random run (default 40)
#     --quick        1 seed, 3 random seeds
#     --record DIR   copy the compact records (results.tsv, summary.txt, coverage report, scoreboard totals) into DIR
# t_bp runs on both snapshots (the transmit MAC paused one clock in 33, and never paused). t_seq_poison is the minimal test of the sequence-number finding of brief 170 (fixed by brief 176): a poisoned
# frame consumes no TCP sequence number; it is an ordinary directed test now and every run checks SEQ exactly (no waiver). Simulation-only: no heavy slot while load < 6 and more than 12 GB free,
# which this script waits for before every run (up to 30 minutes).
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/build"; SEEDS=2; RAND=10; ROUNDS=40; REC=""; SKIP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2;; --seeds) SEEDS="$2"; shift 2;; --rand) RAND="$2"; shift 2;; --rounds) ROUNDS="$2"; shift 2;; --quick) SEEDS=1; RAND=3; shift;;
    --record) REC="$2"; shift 2;; --skip-build) SKIP=1; shift;; *) echo "unknown option $1"; exit 2;;
  esac
done
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"; [ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +u; source "$SETTINGS" >/dev/null 2>&1; set -u
DIRECTED="t_smoke t_mold t_tail t_badfcs t_bp t_book t_risk t_hdr t_seq_poison"
RANDOMT="t_mix t_rand"
SCOPE=""; systemd-run --user --scope -p MemoryMax=3G true >/dev/null 2>&1 && SCOPE="systemd-run --user --scope -q -p MemoryMax=3G nice -n 15"

wait_for_machine() {
  local n=0
  while :; do
    local load avail
    load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
    if awk -v l="$load" -v a="$avail" 'BEGIN{exit !(l < 6 && a > 12)}'; then return 0; fi
    n=$((n+1)); [ $n -gt ${WAIT_MAX:-90} ] && { echo "machine busy (load $load, ${avail} GB free) for 30 minutes; stopping"; exit 3; }
    sleep 20
  done
}
# run_one <build dir> <test> <seed> <run dir> <snapshot> [extra plusarg]  -> "PASS|FAIL errors"
run_one() {
  local b="$1" t="$2" s="$3" d="$4" snap="$5" extra="${6:-}" log
  mkdir -p "$d"; log="$d/run.log"
  wait_for_machine
  ( cd "$b" && $SCOPE xsim "$snap" -runall -sv_seed "$s" -testplusarg "UVM_TESTNAME=$t" -testplusarg "SEED=$s" -testplusarg "ROUNDS=$ROUNDS" $extra -log "$log" >/dev/null 2>&1 )
  local res errs
  res=$(grep -aE "\[RESULT\] (PASS|FAIL)" "$log" | tail -1)
  case "$res" in *PASS*) echo -n "PASS ";; *) echo -n "FAIL ";; esac
  errs=$(grep -aE "^UVM_(ERROR|FATAL) .*@ " "$log" | wc -l)
  echo "$errs"
}

if [ "$SKIP" = 0 ]; then
  echo "== build"; "$HERE/scripts/uvm_build.sh" "$OUT/build_clean" || { echo "BUILD FAILED"; exit 1; }
fi
printf "test\tsnapshot\tseed\tresult\tuvm_errors_and_fatals\n" > "$OUT/results.tsv"
echo "== regression"
for t in $DIRECTED; do for s in $(seq 1 "$SEEDS"); do
  r=$(run_one "$OUT/build_clean" "$t" "$s" "$OUT/runs/${t}_$s" itch_uvm); printf "%s\titch_uvm\t%s\t%s\n" "$t" "$s" "${r// /	}" >> "$OUT/results.tsv"; echo "  $t seed $s: $r"
done; done
for s in $(seq 1 "$SEEDS"); do
  r=$(run_one "$OUT/build_clean" t_bp "$s" "$OUT/runs/t_bp_np_$s" itch_uvm_np); printf "t_bp\titch_uvm_np\t%s\t%s\n" "$s" "${r// /	}" >> "$OUT/results.tsv"; echo "  t_bp (no pause) seed $s: $r"
done
for t in $RANDOMT; do for s in $(seq 1 "$RAND"); do
  snap=itch_uvm; [ $((s % 3)) = 0 ] && snap=itch_uvm_np
  r=$(run_one "$OUT/build_clean" "$t" "$s" "$OUT/runs/${t}_$s" $snap); printf "%s\t%s\t%s\t%s\n" "$t" "$snap" "$s" "${r// /	}" >> "$OUT/results.tsv"; echo "  $t seed $s ($snap): $r"
done; done
NRUN=$(($(wc -l < "$OUT/results.tsv") - 1)); NFAIL=$(awk -F'\t' 'NR>1 && $4!="PASS"' "$OUT/results.tsv" | wc -l)
echo "== coverage merge"
python3 "$HERE/scripts/cov_merge.py" "$OUT" "$OUT"/runs/*/run.log | tee "$OUT/cov_merge.txt"
grep -ah "SB_SUMMARY\] check=" "$OUT"/runs/*/run.log | sed -n -E 's/.*check=([A-Z0-9_]+) compared=([0-9]+) mismatches=([0-9]+).*/\1 \2 \3/p' \
  | awk '{c[$1]+=$2; m[$1]+=$3} END{for(k in c) printf "%s\t%d\t%d\n", k, c[k], m[k]}' | sort > "$OUT/scoreboard_totals.tsv"
{
  echo "regression: $NRUN runs, $NFAIL failed"
  echo "scoreboard checks (check, comparisons, mismatches; SEQ = TCP sequence numbers, exact, no waiver):"; sed 's/^/  /' "$OUT/scoreboard_totals.tsv"
  cat "$OUT/cov_merge.txt"
} | tee "$OUT/summary.txt"
if [ -n "$REC" ]; then
  mkdir -p "$REC"
  cp "$OUT/results.tsv" "$OUT/summary.txt" "$OUT/coverage_report.md" "$OUT/coverage_merged.tsv" "$OUT/sva_cover.tsv" "$OUT/scoreboard_totals.tsv" "$REC/"
  python3 "$HERE/scripts/make_record.py" "$OUT" "$REC"
fi
[ "$NFAIL" = 0 ]
