#!/bin/bash
# Local fresh evidence (brief 143d): re-run the expensive evidence that cannot run on a GitHub runner (xsim UVM and the whole b96 test directory, the
# full SymbiYosys set, the b119 out-of-context Vivado build) from the current tree of a checkout, write fresh records the same way the nightly workflow
# does (python -m flow.fresh_evidence), and compare them with the committed records.
#
#   tools/fresh_evidence_local.sh [--jobs "b96-full-xsim b96-formal-full b119-ooc-vivado"] [--out DIR] [--list]
#
# Default jobs: every `local` tier job of flow/fresh_evidence.py. Output: DIR (default build/fresh_evidence/<date>), with report.md, differs.json and
# the marked matrices; DIR is also linked from build/fresh_evidence/latest. Exit 1 if a committed record differs. It never changes a committed file.
# It uses no model tokens. Heavy jobs (xsim, Vivado) take a heavy slot first and run under a memory cap (CLAUDE.md rule 4); the slot is released only if
# the lock still holds this script's text. Environment: FDA_HEAVY_DIR (default /home/brendan/Claude_sandbox/_handoff), FDA_FRESH_MEMMAX (default 8G).
# A systemd user timer for it is proposed in tools/systemd/ (not enabled).
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PY=${FDA_PYTHON:-python3}
HEAVY=${FDA_HEAVY_DIR:-/home/brendan/Claude_sandbox/_handoff}
MEMMAX=${FDA_FRESH_MEMMAX:-8G}
stamp=$(date +%Y%m%d_%H%M%S)
out=""; jobs=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs) jobs="$2"; shift 2;;
    --out) out="$2"; shift 2;;
    --list) exec "$PY" -m flow.fresh_evidence list --tier local;;
    *) echo "unknown argument $1" >&2; exit 2;;
  esac
done
[ -n "$jobs" ] || jobs=$("$PY" -m flow.fresh_evidence list --tier local | cut -f1 | tr '\n' ' ')
[ -n "$out" ] || out="$ROOT/build/fresh_evidence/$stamp"
mkdir -p "$out"
# Vivado/xsim for the jobs that need it (the path the b96 UVM test also looks for)
[ -f "${XSIM_SETTINGS:-/nonexistent}" ] || { [ -f "$HOME/Xilinx/2026.1/Vivado/settings64.sh" ] && export XSIM_SETTINGS="$HOME/Xilinx/2026.1/Vivado/settings64.sh"; }
[ -d "${FDA_OSS_CAD:-/nonexistent}" ] || { [ -d "$HOME/.local/opt/oss-cad-suite" ] && export FDA_OSS_CAD="$HOME/.local/opt/oss-cad-suite"; }
status=0
for j in $jobs; do
  heavy=$("$PY" -c "import flow.fresh_evidence as F; print(int(bool(F.JOBS['$j'].get('heavy'))))" 2>/dev/null) || { echo "unknown job $j" >&2; status=2; continue; }
  lock=""
  text="fresh-evidence: $j, $(date +%H:%M), expected end $(date -d '+3 hours' +%H:%M)$([ "$j" = b119-ooc-vivado ] && echo ', Vivado impl, peak 6G' || echo ', no Vivado')"
  if [ "$heavy" = 1 ]; then
    for _ in $(seq 1 120); do                     # wait up to two hours for a slot, re-trying every minute
      lock=$("$HEAVY/take_heavy_slot.sh" "$text") && break
      lock=""; sleep 60
    done
    [ -n "$lock" ] || { echo "$j: no heavy slot within two hours; skipped" >&2; status=1; continue; }
    echo "$j: heavy slot $lock"
  fi
  if command -v systemd-run >/dev/null 2>&1; then
    systemd-run --user --scope -q -p MemoryMax="$MEMMAX" "$PY" -m flow.fresh_evidence run "$j" --out "$out" || status=1
  else
    "$PY" -m flow.fresh_evidence run "$j" --out "$out" || status=1
  fi
  if [ -n "$lock" ]; then
    case "$(cat "$lock")" in "fresh-evidence:"*) rm -f "$lock";; esac     # only a lock whose text is ours
  fi
done
rc=0
"$PY" -m flow.fresh_evidence compare --fresh "$out" --json "$out/differs.json" --md "$out/report.md" >/dev/null || rc=$?
for d in designs/*/verif/testplan.yaml; do "$PY" -m flow.trace_v1 write "$(dirname "$(dirname "$d")")" --fresh "$out" >/dev/null; done
mkdir -p "$ROOT/build/fresh_evidence" && ln -sfn "$out" "$ROOT/build/fresh_evidence/latest"
echo "fresh evidence written to $out; report: $out/report.md"
[ $rc -eq 0 ] && echo "every re-run record agrees with its committed record" || echo "A COMMITTED RECORD DIFFERS FROM THE FRESH RUN: see $out/report.md"
[ $rc -ne 0 ] && exit 1
exit $status
