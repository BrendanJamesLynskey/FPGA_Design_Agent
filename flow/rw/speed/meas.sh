#!/usr/bin/env bash
# meas.sh <tag> <outdir> <vivado|rw> <args...>: one timed job of brief 100B in its own memory-capped systemd scope, one record <outdir>/<tag>.meas.json.
#   vivado: args = <tcl file>        (Vivado 2026.1 batch, 1 thread by the tcl: B100_THREADS, default 1)
#   rw:     args = <py script> [...] (the pinned RapidWright venv python, Vivado's JRE, Vivado 2026.1 first on PATH)
# Records: wall seconds, CPU seconds (cgroup cpu.stat of the scope: all processes, user+system), peak memory (cgroup memory.peak, page cache
# included) and the load average and other Vivado processes at the start and the end. Refuses to start while another Vivado runs (timing
# comparisons run alone; brief 100B). The caller holds the heavy slot. Parameters reach the job through B100_* environment variables.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."
TAG="$1"; OUT="$2"; KIND="$3"; shift 3
mkdir -p "$OUT"
if [ "${B100B_INNER:-0}" != 1 ]; then
  if pgrep -x vivado >/dev/null; then echo "meas: another Vivado is running; refusing" >&2; exit 3; fi
  export B100B_INNER=1
  exec systemd-run --user --scope -q -p MemoryMax="${B100_MEM:-6G}" bash "$0" "$TAG" "$OUT" "$KIND" "$@"
fi
CG="/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)"
VIVADO="$(python3 "$ROOT/flow/version_pin.py" --vivado)"
L0=$(cut -d' ' -f1-3 /proc/loadavg); NV0=$(pgrep -xc vivado || true)
S=$(date +%s.%N)
rc=0
if [ "$KIND" = vivado ]; then
  mkdir -p "$OUT/$TAG.d"; cd "$OUT/$TAG.d"      # clockInfo.txt and similar files land in the working directory
  nice -n 15 "$VIVADO" -mode batch -nojournal -nolog -source "$1" > "$OUT/$TAG.log" 2>&1 || rc=$?
else
  VIVBIN="$(dirname "$VIVADO")"
  JH="$(python3 -c "import runpy; print(runpy.run_path('$ROOT/flow/rapidwright_pin.py')['JAVA_HOME'])")"
  export JAVA_HOME="$JH" PATH="$VIVBIN:$JH/bin:$PATH"
  mkdir -p "$OUT/$TAG.d"; cd "$OUT/$TAG.d"
  nice -n 15 "$ROOT/tools/rapidwright_env/venv/bin/python" -I "$@" > "$OUT/$TAG.log" 2>&1 || rc=$?
fi
E=$(date +%s.%N)
CPU=$(awk '/^usage_usec/ {print $2/1e6}' "$CG/cpu.stat")
L1=$(cut -d' ' -f1-3 /proc/loadavg)
python3 - "$OUT/$TAG.meas.json" "$TAG" "$KIND" "$S" "$E" "$CPU" "$(cat "$CG/memory.peak")" "$L0" "$L1" "$NV0" "$rc" <<'PY'
import json, sys
f, tag, kind, s, e, cpu, peak, l0, l1, nv0, rc = sys.argv[1:]
json.dump({"tag": tag, "kind": kind, "wall_s": round(float(e) - float(s), 2), "cpu_s": round(float(cpu), 2),
           "peak_mib": round(int(peak) / 2**20), "load_start": l0, "load_end": l1, "vivado_procs_at_start_excl_self": int(nv0), "rc": int(rc)},
          open(f, "w"), indent=1)
PY
exit $rc
