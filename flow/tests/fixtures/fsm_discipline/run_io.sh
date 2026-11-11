#!/usr/bin/env bash
# run_io.sh: the controller on real pins (measure_io.tcl), placed and routed; one Vivado per variant, a unique systemd scope each.
#   flow/tests/fixtures/fsm_discipline/run_io.sh <out dir>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="${1:?out dir}"; mkdir -p "$OUT"
while IFS='|' read -r name gen iob; do
  case "$name" in \#*|"") continue;; esac
  echo "== $name $(date +%T)"
  systemd-run --user --scope -q --unit="fda-b24-$name-$$" -p MemoryMax=6G nice -n 15 \
    /opt/Xilinx/2025.2/Vivado/bin/vivado -mode batch -log "$OUT/$name.log" -nojournal -source "$HERE/measure_io.tcl" \
    -tclargs "$name" "$gen" "$iob" "$OUT" > "$OUT/$name.stdout" 2>&1 || echo "FAILED $name"
done <<'LIST'
# name|generics|IOB property 0/1
io_out0|OUT=0 IN=0|0
io_out0_iob|OUT=0 IN=0|1
io_out1|OUT=1 IN=0|0
io_out1_iob|OUT=1 IN=0|1
io_out2|OUT=2 IN=0|0
io_out2_iob|OUT=2 IN=0|1
io_in1|OUT=1 IN=1|0
io_in1_iob|OUT=1 IN=1|1
LIST
