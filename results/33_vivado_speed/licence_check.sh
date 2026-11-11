#!/usr/bin/env bash
# licence_check.sh (brief 33): run licence_check.tcl with every licence hidden from Vivado; writes licence_check.log.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
EMPTY="$(mktemp -d)"
cd "$EMPTY"
env -u XILINXD_LICENSE_FILE -u LM_LICENSE_FILE HOME="$EMPTY" \
  systemd-run --user --scope --quiet --unit="${UNIT:-b33-licence-check}" -p MemoryMax=4G nice -n 15 \
  /opt/Xilinx/2025.2/Vivado/bin/vivado -mode batch -nojournal -nolog -source "$HERE/licence_check.tcl" > "$HERE/licence_check.log" 2>&1
echo "exit $?"
grep -E "LICENCE-CHECK|[Ll]icen[cs]e" "$HERE/licence_check.log" | grep -v '^#' | sort -u | head -40
cd /; rm -rf "$EMPTY"
