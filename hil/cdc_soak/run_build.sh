#!/usr/bin/env bash
# run_build.sh: build the CDC soak rig with Vivado, one run at a time, memory-capped.
#
#   hil/cdc_soak/run_build.sh <small|full> [place directive] [route directive]
#
# Refuses to start beside another Vivado. Runs Vivado in a transient systemd scope (MemoryMax, default 12G) under
# nice 15. Output: hil/cdc_soak/build/<mode>[_<place>_<route>]/ (not committed). It never opens the hardware
# manager and never programs a board. On the shared PC, take a heavy slot first (_handoff/take_heavy_slot.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VIVADO="${VIVADO:-/opt/Xilinx/2025.2/Vivado/bin/vivado}"
MODE="${1:?usage: run_build.sh <small|full> [place directive] [route directive]}"
PD="${2:-Default}"
RD="${3:-Default}"
case "$MODE" in small|full) ;; *) echo "mode must be small or full" >&2; exit 1 ;; esac
NAME="$MODE"; [ "$PD/$RD" = "Default/Default" ] || NAME="${MODE}_${PD}_${RD}"
OUT="$HERE/build/$NAME"
n="$(pgrep -af 'unwrapped/lnx64.o/vivado' | grep -vc task_worker.tcl || true)"
[ "${n:-0}" -eq 0 ] || { echo "run_build: another Vivado is running; refusing" >&2; exit 1; }
BID="$(git -C "$HERE" rev-parse --short=8 HEAD 2>/dev/null || echo 00000000)"
mkdir -p "$OUT"
start=$(date +%s)
(cd "$OUT" && systemd-run --user --scope --quiet --unit="cdc-rig-$$" -p MemoryMax="${MEM_MAX:-12G}" \
    nice -n 15 /usr/bin/time -v -o "$OUT/time.txt" \
    "$VIVADO" -mode batch -nojournal -log "$OUT/vivado.log" -source "$HERE/tcl/build.tcl" \
    -tclargs "$MODE" "$OUT" "$PD" "$RD" "$BID") || rc=$?
echo "run_build: $NAME finished in $(( $(date +%s) - start )) s, exit ${rc:-0}; peak RSS $(grep 'Maximum resident' "$OUT/time.txt" | awk '{print $NF}') kB"
exit "${rc:-0}"
