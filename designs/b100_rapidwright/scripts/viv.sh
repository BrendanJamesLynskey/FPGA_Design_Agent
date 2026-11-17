#!/usr/bin/env bash
# viv.sh <tcl> [outdir-for-log]: run one brief 100 Vivado script in a memory-capped scope (1 thread). Parameters through B100_* variables.
# Take a heavy slot first (_handoff/take_heavy_slot.sh "100: ..."). Records the scope's peak memory beside the log.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TCL="$1"; LOG="${2:-/dev/null}"
VIVADO="$(python3 "$HERE/../../../flow/version_pin.py" --vivado)"
cd "$(dirname "$LOG")"   # Vivado drops clockInfo.txt and similar files into its working directory
exec systemd-run --user --scope -p MemoryMax="${B100_MEM:-6G}" bash "$HERE/peak.sh" "${LOG%.log}.time" nice -n 15 \
  "$VIVADO" -mode batch -nojournal -nolog -source "$TCL" > "$LOG" 2>&1
