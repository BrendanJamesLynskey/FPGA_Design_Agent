#!/usr/bin/env bash
# run_regress.sh: the one-command regression of the b96 PCS and MAC UVM bench (brief 112): build, run every test over its seeds, merge the coverage,
# optionally run the seeded-bug (mutant) set; print a pass/fail summary.
#   scripts/run_regress.sh [--out DIR] [--seeds N] [--rand N] [--quick] [--mutants] [--only "m1 m2"] [--record DIR]
#     --out DIR     where builds, logs and reports go (default: verif/uvm/build, git-ignored)
#     --seeds N     seeds per directed test (default 2); --rand N seeds for each constrained-random test (default 10); --quick = 1 and 3
#     --mutants     afterwards build and run each mutant of mutants/mutants.tsv until a test fails (see scripts/mutate.py)
#     --only "..."  with --mutants: only these mutant ids
#     --mutants-only  with --mutants: skip the regression and the coverage merge (reuses the files already in --out)
#     --record DIR  copy the compact records (results.tsv, summary.txt, coverage report, mutants.tsv) into DIR
# Each xsim run is a simulation of a few hundred MB for under ten seconds. The machine rule for simulation-only runs: no heavy slot while the
# 1-minute load is under 6 and more than 12 GB is free; this script waits (up to 30 minutes per run) until both hold.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DESIGN="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/build"; SEEDS=2; RAND=10; MUT=0; ONLY=""; REC=""; MONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2;; --seeds) SEEDS="$2"; shift 2;; --rand) RAND="$2"; shift 2;; --quick) SEEDS=1; RAND=3; shift;;
    --mutants) MUT=1; shift;; --mutants-only) MUT=1; MONLY=1; shift;; --only) ONLY="$2"; shift 2;; --record) REC="$2"; shift 2;; *) echo "unknown option $1"; exit 2;;
  esac
done
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"; [ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +u; source "$SETTINGS" >/dev/null 2>&1; set -u
DIRECTED="t_smoke t_lens t_gaps t_badfcs t_xg t_line_blocks t_hdr t_slip t_ber t_rxreset t_offsets"
RANDOMT="t_rand t_rand_line"
SCOPE=""; systemd-run --user --scope -p MemoryMax=3G true >/dev/null 2>&1 && SCOPE="systemd-run --user --scope -q -p MemoryMax=3G nice -n 15"

wait_for_machine() {
  local n=0
  while :; do
    local load avail
    load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
    if awk -v l="$load" -v a="$avail" 'BEGIN{exit !(l < 6 && a > 12)}'; then return 0; fi
    n=$((n+1)); [ $n -gt 90 ] && { echo "machine busy (load $load, ${avail} GB free) for 30 minutes: running anyway would break the rule; stopping"; exit 3; }
    sleep 20
  done
}

# run_one <build dir> <test> <seed> <run dir>   -> prints "PASS|FAIL errors sva_fail simtime"
run_one() {
  local b="$1" t="$2" s="$3" d="$4" log
  mkdir -p "$d"; log="$d/run.log"
  wait_for_machine
  ( cd "$b" && $SCOPE xsim pcs_uvm -runall -sv_seed "$s" -testplusarg "UVM_TESTNAME=$t" -testplusarg "SEED=$s" -testplusarg "COV_OUT=$d/cov.txt" \
      -log "$log" >/dev/null 2>&1 )
  local res errs
  res=$(grep -aE "\[RESULT\] (PASS|FAIL)" "$log" | tail -1)
  case "$res" in *PASS*) echo -n "PASS ";; *) echo -n "FAIL ";; esac
  errs=$(grep -aE "^UVM_(ERROR|FATAL) .*@ " "$log" | wc -l)
  echo "$errs $(grep -a 'Simulation Memory Usage' "$log" | sed -E 's/.*Peak: ([0-9]+) KB.*/\1/' | head -1)"
}

if [ "$MONLY" = 0 ]; then
echo "== build (clean RTL)"
"$HERE/scripts/uvm_build.sh" "$OUT/build_clean" || { echo "BUILD FAILED"; exit 1; }
printf "test\tseed\tresult\tuvm_errors_and_fatals\tpeak_kb\n" > "$OUT/results.tsv"
echo "== regression"
for t in $DIRECTED; do for s in $(seq 1 "$SEEDS"); do
  r=$(run_one "$OUT/build_clean" "$t" "$s" "$OUT/runs/${t}_$s"); printf "%s\t%s\t%s\n" "$t" "$s" "${r// /	}" >> "$OUT/results.tsv"; echo "  $t seed $s: $r"
done; done
for t in $RANDOMT; do for s in $(seq 1 "$RAND"); do
  r=$(run_one "$OUT/build_clean" "$t" "$s" "$OUT/runs/${t}_$s"); printf "%s\t%s\t%s\n" "$t" "$s" "${r// /	}" >> "$OUT/results.tsv"; echo "  $t seed $s: $r"
done; done
NRUN=$(($(wc -l < "$OUT/results.tsv") - 1)); NFAIL=$(awk -F'\t' 'NR>1 && $3!="PASS"' "$OUT/results.tsv" | wc -l)

echo "== coverage merge"
python3 "$HERE/scripts/cov_merge.py" "$OUT" "$OUT"/runs/*/cov.txt "$OUT"/runs/*/run.log | tee "$OUT/cov_merge.txt"
# scoreboard totals over all runs: compared and mismatches per check
grep -ah "SB_SUMMARY\] check=" "$OUT"/runs/*/run.log | sed -n -E 's/.*check=([A-Z0-9_]+) compared=([0-9]+) mismatches=([0-9]+).*/\1 \2 \3/p' \
  | awk '{c[$1]+=$2; m[$1]+=$3} END{for(k in c) printf "%s\t%d\t%d\n", k, c[k], m[k]}' | sort > "$OUT/scoreboard_totals.tsv"
{
  echo "regression: $NRUN runs, $NFAIL failed"
  echo "scoreboard checks (check, comparisons, mismatches):"; sed 's/^/  /' "$OUT/scoreboard_totals.tsv"
  cat "$OUT/cov_merge.txt"
} | tee "$OUT/summary.txt"

fi
if [ "$MUT" = 1 ]; then
  echo "== mutants"
  MUT_TESTS="t_smoke t_lens t_xg t_line_blocks t_hdr t_badfcs t_gaps t_offsets t_rxreset t_slip t_ber t_rand:1 t_rand:2 t_rand_line:1 t_rand_line:2"
  printf "id\tverdict\tkilled_by\tchecks_that_fired\twhat\n" > "$OUT/mutants.tsv"
  for id in $(python3 "$HERE/scripts/mutate.py" list | cut -f1); do
    if [ -n "$ONLY" ] && ! echo " $ONLY " | grep -q " $id "; then continue; fi
    what=$(python3 "$HERE/scripts/mutate.py" list | awk -F'\t' -v i="$id" '$1==i{print $3}')
    python3 "$HERE/scripts/mutate.py" make "$id" "$DESIGN/rtl" "$OUT/mut/$id/rtl" || { echo "  $id: mutation did not apply"; printf "%s\tNOT_APPLIED\t-\t-\t%s\n" "$id" "$what" >> "$OUT/mutants.tsv"; continue; }
    "$HERE/scripts/uvm_build.sh" "$OUT/mut/$id/build" "$OUT/mut/$id/rtl" > "$OUT/mut/$id/build.txt" 2>&1 || { echo "  $id: does not build"; printf "%s\tBUILD_FAIL\t-\t-\t%s\n" "$id" "$what" >> "$OUT/mutants.tsv"; continue; }
    verdict=SURVIVED; by="-"; fired="-"
    for tt in $MUT_TESTS; do
      t="${tt%%:*}"; s=1; case "$tt" in *:*) s="${tt##*:}";; esac
      r=$(run_one "$OUT/mut/$id/build" "$t" "$s" "$OUT/mut/$id/runs/${t}_$s")
      case "$r" in FAIL*) verdict=KILLED; by="$t seed $s"
        fired=$(grep -aE "^UVM_ERROR" "$OUT/mut/$id/runs/${t}_$s/run.log" | grep -aoE "\[(SB|SVA)\] [A-Za-z0-9_]*" | sed -E 's/\[SB\] //; s/\[SVA\].*/SVA/' | sort -u | tr '\n' ' ')
        break;; esac
    done
    echo "  $id: $verdict ($by) checks: $fired"
    printf "%s\t%s\t%s\t%s\t%s\n" "$id" "$verdict" "$by" "$fired" "$what" >> "$OUT/mutants.tsv"
  done
  echo "mutants killed: $(awk -F'\t' 'NR>1 && $2=="KILLED"' "$OUT/mutants.tsv" | wc -l) of $(($(wc -l < "$OUT/mutants.tsv") - 1))" | tee -a "$OUT/summary.txt"
fi

if [ -n "$REC" ]; then
  mkdir -p "$REC"
  cp "$OUT/results.tsv" "$OUT/summary.txt" "$OUT/coverage_report.md" "$OUT/coverage_merged.tsv" "$OUT/sva_cover.tsv" "$OUT/scoreboard_totals.tsv" "$REC/"
  [ -f "$OUT/mutants.tsv" ] && cp "$OUT/mutants.tsv" "$REC/"
fi
[ "${NFAIL:-0}" = 0 ]
