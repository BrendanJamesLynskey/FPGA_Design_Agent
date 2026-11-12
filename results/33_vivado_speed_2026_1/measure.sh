#!/usr/bin/env bash
# measure.sh: brief 33's Vivado measurements, repeated on Vivado 2026.1 by brief 49 (6 GB cap for every build, owner rule), one build at a time (the caller holds a heavy slot marked "Vivado impl").
#
#   results/33_vivado_speed/measure.sh <jobs file>
#
# Each line of the jobs file: <label> <design dir | rig> <threads> <stop stage> [VAR=value ...]
#   - a design dir runs flow/run_vivado.sh <dir> base with FDA_VIVADO_THREADS, FDA_STOP_AFTER, FDA_RESULT_HASH=1 and
#     MEM_MAX=8G (plus the extra variables, e.g. FDA_BUILD_CACHE=0 or FDA_INCREMENTAL=1), and copies run.json,
#     gates.json, stages.txt, cache.json, result_hash.json and incremental_reuse.rpt into raw/<label>/;
#   - "rig" runs hil/cdc_soak/run_build.sh full (MemoryMax 12G) and polls its scope (cdc-rig-<pid>.scope) for the
#     peak charged and anonymous memory, the way run_vivado.sh does, then hashes its result_dump.txt.
# Every call's own wall time (including cache hits) goes to raw/<label>/call.json. Lines starting with # are skipped.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${PYTHON:-python3}"
JOBS="$1"

while read -r label design threads stop extra; do
  case "$label" in ''|'#'*) continue ;; esac
  dst="$HERE/raw/$label"
  # a Vivado started outside the heavy slots (another session's probe) would slow the build and make the runner refuse:
  # wait until none is running, and record how long that took
  w0=$(date +%s)
  while [ "$(pgrep -xc vivado || true)" -gt 0 ]; do sleep 15; done
  [ $(( $(date +%s) - w0 )) -gt 0 ] && echo "measure: waited $(( $(date +%s) - w0 )) s for another Vivado to finish"
  rm -rf "$dst"
  mkdir -p "$dst"
  echo "measure: $label ($design, $threads threads, until $stop, ${extra:-no extras}) at $(date +%H:%M:%S)"
  t0=$(date +%s.%N)
  if [ "$design" = rig ]; then
    out="$ROOT/hil/cdc_soak/build/full"
    rm -rf "$out"
    # no FDA_RESULT_HASH here: on the rig the dump took 658 s and most of the memory (first attempt, 2026-11-11), so the
    # build runs clean and hash_dcp.tcl hashes the saved post_route.dcp afterwards (RIG_DCP_DIR)
    env FDA_VIVADO_THREADS="$threads" MEM_MAX=6G bash "$ROOT/hil/cdc_soak/run_build.sh" full >"$dst/stdout.txt" 2>&1 &
    pid=$!
    unit="cdc-rig-$pid"
    peak=0; anon=0; cg=""
    while kill -0 "$pid" 2>/dev/null; do
      [ -z "$cg" ] && cg="$(systemctl --user show -p ControlGroup --value "$unit.scope" 2>/dev/null || true)"
      if [ -n "$cg" ] && [ -r "/sys/fs/cgroup$cg/memory.peak" ]; then
        v="$(cat "/sys/fs/cgroup$cg/memory.peak" 2>/dev/null || echo 0)"; [ "$v" -gt "$peak" ] && peak="$v"
        a="$(awk '$1 == "anon" {print $2}' "/sys/fs/cgroup$cg/memory.stat" 2>/dev/null || echo 0)"
        [ -n "$a" ] && [ "$a" -gt "$anon" ] && anon="$a"
      fi
      sleep 2
    done
    wait "$pid"; rc=$?
    t1=$(date +%s.%N)
    for f in stages.txt timing_summary.rpt time.txt; do cp "$out/$f" "$dst/" 2>/dev/null || true; done
    if [ -n "${RIG_DCP_DIR:-}" ]; then mkdir -p "$RIG_DCP_DIR"; cp "$out/post_route.dcp" "$RIG_DCP_DIR/$label.dcp"; fi
    "$PY" - "$dst" "$rc" "$t0" "$t1" "$peak" "$anon" "$threads" "$unit" <<'EOF'
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parents[3]))
from flow.gates import parse_timing_summary
dst, rc, t0, t1, peak, anon, threads, unit = sys.argv[1:]
dst = Path(dst)
t = (dst / "time.txt").read_text() if (dst / "time.txt").exists() else ""
m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
ts = parse_timing_summary((dst / "timing_summary.rpt").read_text()) if (dst / "timing_summary.rpt").exists() else {}
call = {"design": "hil/cdc_soak full", "exit_code": int(rc), "wall_s": round(float(t1) - float(t0), 1),
        "threads": int(threads), "scope_unit": unit, "memory_cap": "6G",
        "scope_memory_peak_mib": round(int(peak) / 2**20), "scope_anon_peak_mib": round(int(anon) / 2**20),
        "vivado_peak_rss_mib": round(int(m.group(1)) / 1024) if m else None,
        "wns_ns": ts.get("wns_ns"), "whs_ns": ts.get("whs_ns"),
        "stages_s": {l.split()[0]: float(l.split()[1]) for l in (dst / "stages.txt").read_text().splitlines()}
                    if (dst / "stages.txt").exists() else {}}
(dst / "call.json").write_text(json.dumps(call, indent=2) + "\n")
print("measure:", json.dumps({k: call[k] for k in ("exit_code", "wall_s", "scope_anon_peak_mib", "wns_ns")}))
EOF
  else
    # shellcheck disable=SC2086
    env FDA_VIVADO_THREADS="$threads" FDA_STOP_AFTER="$stop" FDA_RESULT_HASH=1 MEM_MAX=6G $extra \
      "$ROOT/flow/run_vivado.sh" "$ROOT/$design" base >"$dst/stdout.txt" 2>&1
    rc=$?
    t1=$(date +%s.%N)
    b="$ROOT/$design/build/base"
    for f in run.json gates.json stages.txt cache.json result_hash.json incremental_reuse.rpt; do
      cp "$b/$f" "$dst/" 2>/dev/null || true
    done
    "$PY" - "$dst" "$rc" "$t0" "$t1" "$design" "$threads" "$stop" "${extra:-}" <<'EOF'
import json, sys
from pathlib import Path
dst, rc, t0, t1, design, threads, stop, extra = sys.argv[1:]
dst = Path(dst)
g = json.loads((dst / "gates.json").read_text()) if (dst / "gates.json").exists() else {}
cache = next((l.split(": ")[-1] for l in (dst / "stdout.txt").read_text().splitlines() if "build cache:" in l), None)
call = {"design": design, "exit_code": int(rc), "wall_s": round(float(t1) - float(t0), 1), "threads": int(threads),
        "stop": stop, "extra": extra, "cache": cache, "wns_ns": (g.get("timing") or {}).get("wns_ns"),
        "whs_ns": (g.get("timing") or {}).get("whs_ns"), "gates_pass": g.get("pass"),
        "gates": g.get("gates")}
(dst / "call.json").write_text(json.dumps(call, indent=2) + "\n")
print("measure:", json.dumps({k: call[k] for k in ("exit_code", "wall_s", "cache", "wns_ns", "gates_pass")}))
EOF
  fi
done <"$JOBS"
echo "measure: done at $(date +%H:%M:%S)"
