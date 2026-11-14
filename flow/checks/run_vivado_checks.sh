#!/usr/bin/env bash
# run_vivado_checks.sh: ONE Vivado session for the check suite (brief 71): open a checkpoint once, run the requested
# reports in sequence (flow/checks/vivado_checks.tcl), memory-capped like a build.
#
#   flow/checks/run_vivado_checks.sh <checkpoint.dcp> <out_dir> <report,report,...>
#
# Same machine rules as flow/run_vivado.sh: Vivado 2026.1 (flow/version_pin.py), systemd-run --user --scope with
# MemoryMax (FDA_VIVADO_MEM, default 6G), nice 15, one thread, and no start while FDA_VIVADO_MAX (default 1) Vivado
# jobs already run. A caller on the shared PC takes a heavy slot first (_handoff/take_heavy_slot.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
die() { echo "run_vivado_checks: $*" >&2; exit 1; }
[ $# -eq 3 ] || die "usage: run_vivado_checks.sh <checkpoint.dcp> <out_dir> <report,report,...>"
DCP="$(realpath "$1")"; OUT="$2"; NAMES="$3"
[ -f "$DCP" ] || die "no checkpoint $1"
case "$NAMES" in *[!a-z_,]*|'') die "report names must be [a-z_] separated by commas" ;; esac
VIVADO="${VIVADO:-$(python3 "$ROOT/flow/version_pin.py" --vivado)}"
[ -x "$VIVADO" ] || die "Vivado not found at $VIVADO"
command -v systemd-run >/dev/null || die "systemd-run not found"
max="${FDA_VIVADO_MAX:-1}"; case "$max" in ''|*[!0-9]*) max=1 ;; esac; [ "$max" -le 2 ] || max=2
n="$(pgrep -af 'unwrapped/lnx64.o/vivado' | grep -vc task_worker.tcl || true)"
if [ -n "${FDA_TEST_VIVADO_RUNNING:-}" ]; then n="$FDA_TEST_VIVADO_RUNNING"; fi
[ "${n:-0}" -lt "$max" ] || die "$n Vivado job(s) running, limit FDA_VIVADO_MAX=$max on this PC"
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
unit="fda-checks-$$"
cd "$OUT"
systemd-run --user --scope --quiet --unit="$unit" -p MemoryMax="${FDA_VIVADO_MEM:-6G}" nice -n 15 \
    "$VIVADO" -mode batch -nojournal -log "$OUT/vivado_checks.log" \
    -source "$ROOT/flow/checks/vivado_checks.tcl" -tclargs "$DCP" "$OUT" "$NAMES" >"$OUT/vivado_checks.stdout" 2>&1 || {
  rc=$?; tail -5 "$OUT/vivado_checks.stdout" >&2; exit "$rc"; }
grep -q FDA-CHECKS-DONE "$OUT/vivado_checks.stdout" || die "Vivado ended without FDA-CHECKS-DONE (see $OUT/vivado_checks.log)"
grep '^FDA-CHECK ' "$OUT/vivado_checks.stdout" || true
