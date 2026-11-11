#!/bin/bash
# run_batch_remote.sh: run a batch of Vivado builds on the burst instance (called by cloud/fda_cloud.py run-batch).
#
#   PARALLEL=2 THREADS=4 MEM_MAX=7G bash cloud/instance/run_batch_remote.sh batch.txt
#
# Each line of the batch file: <label> <design dir> <stop stage> [VAR=value ...] (# comments allowed). Every job runs
# in its own copy of the repository (work/<label>/), so jobs on the same design (seeds, strategies, parameter sweeps)
# never share a build directory, through flow/run_vivado.sh with FDA_VIVADO_THREADS=$THREADS and its memory cap.
# Results (run.json, gates.json, stages.txt, the reports the gates read, the job's log) go to cloud_results/<label>/.
# A job whose cloud_results/<label>/done exists is skipped, so after a Spot interruption the same batch re-runs only
# the unfinished jobs. /run/fda-busy (or $FDA_BUSY_FILE) holds the idle watchdog off while the batch runs.
set -u
BATCH="$1"
PARALLEL="${PARALLEL:-2}"; THREADS="${THREADS:-4}"; MEM_MAX="${MEM_MAX:-7G}"
HERE="$(pwd)"
BUSY="${FDA_BUSY_FILE:-/run/fda-busy}"
VIVADO="${VIVADO:-/tools/Xilinx/2025.2/Vivado/bin/vivado}"
touch "$BUSY" 2>/dev/null || sudo touch "$BUSY"
mkdir -p cloud_results work
job() {
  local label="$1" design="$2" stop="$3"; shift 3
  local res="$HERE/cloud_results/$label"
  [ -f "$res/done" ] && { echo "skip $label (done)"; return 0; }
  mkdir -p "$res"
  rm -rf "$HERE/work/$label"
  rsync -a --exclude work --exclude cloud_results --exclude .git "$HERE/" "$HERE/work/$label/"
  local t0=$(date +%s)
  ( cd "$HERE/work/$label" && env FDA_VIVADO_THREADS="$THREADS" FDA_STOP_AFTER="$stop" MEM_MAX="$MEM_MAX" \
      FDA_VIVADO_MAX=$((PARALLEL + 1)) MIN_AVAIL_GB=3 VIVADO="$VIVADO" "$@" \
      flow/run_vivado.sh "$design" base ) >"$res/log.txt" 2>&1
  local rc=$?
  cp "$HERE/work/$label/$design/build/base/"{run.json,gates.json,stages.txt,timing_summary.rpt,utilization.rpt,power.rpt} \
     "$res/" 2>/dev/null
  echo "{\"label\": \"$label\", \"exit_code\": $rc, \"wall_s\": $(( $(date +%s) - t0 ))}" >"$res/job.json"
  touch "$res/done"
  rm -rf "$HERE/work/$label"
  echo "done $label exit $rc"
}
export -f job
export HERE THREADS MEM_MAX PARALLEL VIVADO
grep -v '^\s*#' "$BATCH" | grep -v '^\s*$' | \
  xargs -P "$PARALLEL" -L 1 bash -c 'sleep $((RANDOM % 5)); job "$@"' _
rm -f "$BUSY" 2>/dev/null || sudo rm -f "$BUSY"
echo "batch done: $(ls cloud_results | wc -l) results in $HERE/cloud_results"
