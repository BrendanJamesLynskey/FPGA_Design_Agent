#!/usr/bin/env bash
# run_vivado.sh: the memory-safe local Vivado runner.
#
#   flow/run_vivado.sh designs/<name> [base|ila|both]      (default: base)
#
# For each variant it:
#   1. refuses to start if another Vivado is running, or if MemAvailable is
#      below MIN_AVAIL_GB (default 7), and says why;
#   2. writes build/<variant>/inputs.tcl (flow/prepare.py);
#   3. runs Vivado in batch mode in a transient systemd scope capped at
#      MemoryMax=6G, under nice 15, with general.maxThreads 1 (set in build.tcl);
#   4. records wall time, the Vivado process's peak RSS (/usr/bin/time -v) and,
#      from the scope's cgroup (polled every 2 s), its peak charged memory
#      (memory.peak, page cache included), its peak anonymous memory (all
#      processes), its peak swap, and how often the cap was hit, in run.json;
#   5. runs the gates (flow/gates.py) into gates.json.
# Variants run one after the other, never together. Logs: designs/<name>/build/<variant>/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VIVADO="${VIVADO:-/opt/Xilinx/2025.2/Vivado/bin/vivado}"
PY="${PYTHON:-python3}"
MIN_AVAIL_GB="${MIN_AVAIL_GB:-7}"
MEM_MAX="${MEM_MAX:-6G}"

die() { echo "run_vivado: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: flow/run_vivado.sh designs/<name> [base|ila|both]"
DESIGN="$(cd "$1" && pwd)" || die "no design directory $1"
REL="${DESIGN#"$ROOT"/}"
[ -f "$DESIGN/build.yaml" ] || die "$REL has no build.yaml"
case "${2:-base}" in
  base) VARIANTS=(base) ;;
  ila)  VARIANTS=(ila) ;;
  both) VARIANTS=(base ila) ;;
  *) die "variant must be base, ila or both" ;;
esac
[ -x "$VIVADO" ] || die "Vivado not found at $VIVADO (set VIVADO=...)"
command -v systemd-run >/dev/null || die "systemd-run not found"

preflight() {
  # pgrep -x matches the process name exactly, so it never matches this script
  local running
  running="$(pgrep -x -d, vivado || true)"
  [ -z "$running" ] || die "another Vivado is running (PIDs $running); one Vivado job at a time on this PC"
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
  preflight
  rm -rf "$out"
  mkdir -p "$out"
  local prep
  prep="$("$PY" "$ROOT/flow/prepare.py" "$DESIGN" --variant "$variant" --out "$out")"
  echo "$prep" >"$out/prepare.json"

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

  "$PY" - "$out" "$rc" "$t_start" "$t_end" "$peak" "$MEM_MAX" "$REL" "$variant" "$VIVADO" \
      "$anon" "$swap" "$hits" "$ooms" <<'EOF'
import json, re, subprocess, sys
from pathlib import Path
out, rc, t0, t1, peak, cap, rel, variant, vivado, anon, swap, hits, ooms = sys.argv[1:]
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
    "memory_cap": cap, "max_threads": 1, "nice": 15,
    "vivado_version": ver.group(1) if ver else None,
    "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
    "build_stamp": prep["build_stamp"], "sources_sha256": prep["sources_sha256"],
    "stages_s": {l.split()[0]: float(l.split()[1]) for l in (out / "stages.txt").read_text().splitlines()}
                if (out / "stages.txt").exists() else {},
}
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
  "$PY" "$ROOT/flow/gates.py" "$out" --json "$out/gates.json"
}

status=0
for v in "${VARIANTS[@]}"; do
  run_variant "$v" || status=$?
done
exit "$status"
