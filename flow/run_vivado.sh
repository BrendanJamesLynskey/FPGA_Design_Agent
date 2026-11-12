#!/usr/bin/env bash
# run_vivado.sh: the memory-safe local Vivado runner.
#
#   flow/run_vivado.sh designs/<name> [base|ila|both]      (default: base)
#   flow/run_vivado.sh designs/<name> program|program-ila  (program the board's SRAM:
#       hands over to flow/program.py, which applies the same guard rails, the
#       USB-power gate and the build-stamp check; flash is never written)
#
# For each variant it:
#   1. refuses to start if another Vivado is running, or if MemAvailable is
#      below MIN_AVAIL_GB (default 7), and says why;
#   2. writes build/<variant>/inputs.tcl (flow/prepare.py);
#   3. reuses an earlier build of the same inputs where it can (flow/build_cache.py,
#      brief 33): the same flow key and the requested stage already reached is a
#      cache hit (no Vivado, the gates re-run); an earlier stage reached resumes
#      from its post_synth.dcp or post_route.dcp; FDA_BUILD_CACHE=0 turns this off;
#   4. otherwise runs Vivado in batch mode in a transient systemd scope capped at
#      MemoryMax=6G, under nice 15, with FDA_VIVADO_THREADS threads (default 2;
#      flow/build.tcl; _handoff/take_heavy_slot.sh --env sets it on the shared PC);
#   5. records wall time, the Vivado process's peak RSS (/usr/bin/time -v) and,
#      from the scope's cgroup (polled every 2 s), its peak charged memory
#      (memory.peak, page cache included), its peak anonymous memory (all
#      processes), its peak swap, how often the cap was hit, the thread count and
#      the cache decision, in run.json (FDA_RESULT_HASH=1 adds the placement and
#      routing hashes of flow/result_hash.py);
#   6. runs the gates (flow/gates.py) into gates.json.
# Variants run one after the other, never together. Logs: designs/<name>/build/<variant>/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VIVADO="${VIVADO:-$(python3 "$ROOT/flow/version_pin.py" --vivado)}"
PY="${PYTHON:-python3}"
MIN_AVAIL_GB="${MIN_AVAIL_GB:-7}"
MEM_MAX="${MEM_MAX:-6G}"
# brief 33: 1, 2 and 4 threads gave the same placement, routing and WNS on three designs (results/33_vivado_speed), so the
# default is 2, safe beside a second Vivado job on the 4-core build PC; take_heavy_slot.sh --env sets 4 when it runs alone
THREADS="${FDA_VIVADO_THREADS:-2}"
case "$THREADS" in [1-8]) ;; *) echo "run_vivado: FDA_VIVADO_THREADS must be 1-8, not $THREADS" >&2; exit 1 ;; esac
export FDA_VIVADO_THREADS="$THREADS"

die() { echo "run_vivado: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: flow/run_vivado.sh designs/<name> [base|ila|both|program|program-ila]"
DESIGN="$(cd "$1" && pwd)" || die "no design directory $1"
REL="${DESIGN#"$ROOT"/}"
[ -f "$DESIGN/build.yaml" ] || die "$REL has no build.yaml"
case "${2:-base}" in
  program)     exec "$PY" "$ROOT/flow/program.py" "$DESIGN" base "${@:3}" ;;
  program-ila) exec "$PY" "$ROOT/flow/program.py" "$DESIGN" ila "${@:3}" ;;
  base) VARIANTS=(base) ;;
  ila)  VARIANTS=(ila) ;;
  both) VARIANTS=(base ila) ;;
  *) die "variant must be base, ila, both, program or program-ila" ;;
esac
[ -x "$VIVADO" ] || die "Vivado not found at $VIVADO (set VIVADO=...)"
command -v systemd-run >/dev/null || die "systemd-run not found"

preflight() {
  # pgrep -x matches the process name exactly, so it never matches this script
  # FDA_VIVADO_MAX (default 1) is how many Vivado jobs may run at once; the owner may raise it to 2 on the 32 GB PC
  # (2026-11-07 trial, measured by _handoff/fpga_agent/resources/vivado_monitor.sh). It counts the real binaries.
  local running n max="${FDA_VIVADO_MAX:-1}"
  # capped at 2: the owner's limit of two heavy jobs on this PC (a non-number counts as 1)
  case "$max" in ''|*[!0-9]*) max=1 ;; esac
  [ "$max" -ge 1 ] || max=1
  [ "$max" -le 2 ] || max=2
  # Vivado's own task_worker.tcl helpers (synthesis children) are part of their parent job, so they are not counted
  running="$(pgrep -af 'unwrapped/lnx64.o/vivado' | grep -v task_worker.tcl | awk '{print $1}' | paste -sd, - || true)"
  n="$(pgrep -af 'unwrapped/lnx64.o/vivado' | grep -vc task_worker.tcl || true)"
  # tests only: a test that runs a fake Vivado sets the count it wants, so other sessions' real jobs on the PC do not
  # decide its result (flow/tests/test_33_build_cache.py)
  if [ -n "${FDA_TEST_VIVADO_RUNNING:-}" ]; then n="$FDA_TEST_VIVADO_RUNNING"; running="(test override)"; fi
  [ "${n:-0}" -lt "$max" ] || die "$n Vivado job(s) running (PIDs $running), limit FDA_VIVADO_MAX=$max on this PC"
  local avail_kb need_kb
  avail_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  need_kb=$((MIN_AVAIL_GB * 1024 * 1024))
  if [ "$avail_kb" -lt "$need_kb" ]; then
    die "only $((avail_kb / 1024)) MiB available, need ${MIN_AVAIL_GB} GiB; close something (Chrome, other builds) and retry"
  fi
  echo "run_vivado: preflight ok ($((avail_kb / 1024)) MiB available, no other Vivado)"
}

run_variant() {
  local variant="$1"
  local out="$DESIGN/build/$variant"
  local prev="$DESIGN/build/$variant.prev"
  # brief 33: the earlier build of this variant is kept aside until the decision (flow/build_cache.py) is made
  rm -rf "$prev"
  if [ -d "$out" ]; then mv "$out" "$prev"; fi
  mkdir -p "$out"
  local prep
  prep="$("$PY" "$ROOT/flow/prepare.py" "$DESIGN" --variant "$variant" --out "$out")"
  echo "$prep" >"$out/prepare.json"
  # the build manifest (flow/manifest.py) and the build ID, appended to inputs.tcl before the cache decision so that the
  # flow key covers it; flow/build.tcl writes it into the bitstream's USR_ACCESS register
  "$PY" "$ROOT/flow/manifest.py" pre "$out" --vivado "$VIVADO" --threads "$THREADS" >/dev/null
  local decision action
  decision="$("$PY" "$ROOT/flow/build_cache.py" "$out" --prev "$prev" --base "$DESIGN/build/base" \
      --variant "$variant" --vivado "$VIVADO" --threads "$THREADS")"
  action="$("$PY" -c 'import json, sys; print(json.loads(sys.argv[1])["action"])' "$decision")"
  echo "run_vivado: build cache: $action"
  if [ "$action" = "hit" ]; then
    # the same inputs already reached the requested stage: put that build back and re-run its gates
    rm -rf "$out"
    mv "$prev" "$out"
    "$PY" -c 'import json, sys, time
from pathlib import Path
rj = Path(sys.argv[1]) / "run.json"
run = json.loads(rj.read_text()) if rj.is_file() else {}
run.setdefault("cache_hits", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                         "requested_rank": json.loads(sys.argv[2])["requested"]})
rj.write_text(json.dumps(run, indent=2) + "\n")' "$out" "$decision"
    echo "run_vivado: $REL $variant: cache hit, Vivado not run (the build in $out has the same inputs)"
    "$PY" "$ROOT/flow/gates.py" "$out" --json "$out/gates.json"
    return
  fi
  # Vivado will run: check the machine first, and put the earlier build back if it refuses
  if ! (preflight); then
    rm -rf "$out"
    if [ -d "$prev" ]; then mv "$prev" "$out"; fi
    exit 1
  fi
  echo "$decision" >"$out/cache.json"

  local unit="fda-vivado-$$-$variant"
  local t_start t_end
  t_start="$(date +%s.%N)"
  # The scope runs from the build dir so Vivado's journal/log/.Xil land there
  (cd "$out" && exec systemd-run --user --scope --quiet --unit="$unit" -p MemoryMax="$MEM_MAX" \
      nice -n 15 /usr/bin/time -v -o "$out/time.txt" \
      "$VIVADO" -mode batch -nojournal -log "$out/vivado.log" \
      -source "$ROOT/flow/build.tcl" -tclargs "$out/inputs.tcl" >"$out/stdout.txt" 2>&1) &
  local pid=$!
  # Poll the scope's cgroup while Vivado runs: memory.peak (all charged memory,
  # page cache included), the largest anonymous total (memory.stat anon: the
  # processes' own memory, summed over every process in the scope), and
  # memory.events (max = times the cap was hit and reclaim ran; oom_kill)
  local peak=0 anon=0 swap=0 hits=0 ooms=0 cg="" v a
  while kill -0 "$pid" 2>/dev/null; do
    if [ -z "$cg" ]; then
      cg="$(systemctl --user show -p ControlGroup --value "$unit.scope" 2>/dev/null || true)"
    fi
    if [ -n "$cg" ] && [ -r "/sys/fs/cgroup$cg/memory.peak" ]; then
      v="$(cat "/sys/fs/cgroup$cg/memory.peak" 2>/dev/null || echo 0)"
      [ "$v" -gt "$peak" ] && peak="$v"
      a="$(awk '$1 == "anon" {print $2}' "/sys/fs/cgroup$cg/memory.stat" 2>/dev/null || echo 0)"
      [ -n "$a" ] && [ "$a" -gt "$anon" ] && anon="$a"
      v="$(cat "/sys/fs/cgroup$cg/memory.swap.peak" 2>/dev/null || echo 0)"
      [ "$v" -gt "$swap" ] && swap="$v"
      v="$(awk '$1 == "max" {print $2}' "/sys/fs/cgroup$cg/memory.events" 2>/dev/null || echo 0)"
      [ -n "$v" ] && hits="$v"
      v="$(awk '$1 == "oom_kill" {print $2}' "/sys/fs/cgroup$cg/memory.events" 2>/dev/null || echo 0)"
      [ -n "$v" ] && ooms="$v"
    fi
    sleep 2
  done
  local rc=0
  wait "$pid" || rc=$?
  t_end="$(date +%s.%N)"
  # the manifest records the tool facts, the outputs and the incremental reference actually used (hashed here, before
  # the earlier build that holds it is removed), and checks that the bitstream carries the build ID
  local manifest_ok=1
  if [ "$rc" -eq 0 ]; then
    "$PY" "$ROOT/flow/manifest.py" post "$out" || manifest_ok=0
  fi
  # the earlier build is no longer needed: a resumed build copied what it used, and an incremental one has finished
  rm -rf "$prev"
  if [ "${FDA_RESULT_HASH:-0}" = "1" ] && [ -f "$out/result_dump.txt" ]; then
    "$PY" "$ROOT/flow/result_hash.py" "$out/result_dump.txt" --json "$out/result_hash.json" >/dev/null || true
  fi

  "$PY" - "$out" "$rc" "$t_start" "$t_end" "$peak" "$MEM_MAX" "$REL" "$variant" "$VIVADO" \
      "$anon" "$swap" "$hits" "$ooms" "$THREADS" "$unit" <<'EOF'
import json, re, subprocess, sys
from pathlib import Path
out, rc, t0, t1, peak, cap, rel, variant, vivado, anon, swap, hits, ooms, threads, unit = sys.argv[1:]
out = Path(out)
t = (out / "time.txt").read_text() if (out / "time.txt").exists() else ""
m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
ver = re.search(r"Vivado v(\S+)", (out / "vivado.log").read_text()) if (out / "vivado.log").exists() else None
def git(*a):
    try:
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=out, check=True).stdout.strip()
    except Exception:
        return ""
prep = json.loads((out / "prepare.json").read_text())
run = {
    "design": rel, "variant": variant, "exit_code": int(rc),
    "wall_s": round(float(t1) - float(t0), 1),
    "vivado_peak_rss_mib": round(int(m.group(1)) / 1024) if m else None,
    "scope_memory_peak_mib": round(int(peak) / 2**20) if int(peak) else None,
    "scope_anon_peak_mib": round(int(anon) / 2**20) if int(anon) else None,
    "scope_swap_peak_mib": round(int(swap) / 2**20),
    "scope_cap_hits": int(hits), "scope_oom_kills": int(ooms),
    "memory_cap": cap, "max_threads": int(threads), "nice": 15, "scope_unit": unit,
    "vivado_version": ver.group(1) if ver else None,
    "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
    "build_stamp": prep["build_stamp"], "sources_sha256": prep["sources_sha256"],
    "stages_s": {l.split()[0]: float(l.split()[1]) for l in (out / "stages.txt").read_text().splitlines()}
                if (out / "stages.txt").exists() else {},
    "cache": json.loads((out / "cache.json").read_text()).get("action") if (out / "cache.json").exists() else None,
    "flow_key": (out / "flow_key.txt").read_text().strip() if (out / "flow_key.txt").exists() else None,
    "build_id": json.loads((out / "manifest.json").read_text()).get("build_id") if (out / "manifest.json").exists() else None,
}
if (out / "result_hash.json").exists():
    run["result_hash"] = json.loads((out / "result_hash.json").read_text())
(out / "run.json").write_text(json.dumps(run, indent=2) + "\n")
print(f"run_vivado: {rel} {variant}: exit {rc}, {run['wall_s']} s, "
      f"Vivado peak RSS {run['vivado_peak_rss_mib']} MiB, scope peak {run['scope_memory_peak_mib']} MiB "
      f"(anon {run['scope_anon_peak_mib']} MiB, swap {run['scope_swap_peak_mib']} MiB; cap {cap} hit {run['scope_cap_hits']} times, OOM kills {run['scope_oom_kills']})")
EOF
  if [ "$rc" -ne 0 ]; then
    tail -n 30 "$out/stdout.txt" >&2 || true
    # If the flow got as far as the reports, the gates still say what is wrong
    if [ -f "$out/power.rpt" ]; then
      "$PY" "$ROOT/flow/gates.py" "$out" --json "$out/gates.json" || true
    fi
    die "Vivado failed for $REL ($variant), exit $rc; see $out/vivado.log"
  fi
  if [ "$manifest_ok" -ne 1 ]; then
    die "the build of $REL ($variant) does not match its manifest (build ID in the bitstream, or the incremental reference); see $out/manifest.json"
  fi
  "$PY" "$ROOT/flow/gates.py" "$out" --json "$out/gates.json"
}

status=0
for v in "${VARIANTS[@]}"; do
  run_variant "$v" || status=$?
done
exit "$status"
