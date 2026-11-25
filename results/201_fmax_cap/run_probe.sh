#!/bin/bash
# Brief 201: re-run the clock-buffer probe on three more parts (three routed out-of-context runs, one thread). Takes a heavy slot first:
#   _handoff/take_heavy_slot.sh "201: Vivado impl OOC 3 small BUFG pulse-width probe runs, <start>, expected end <hh:mm>, peak 3G"
# Run from the repository root; Vivado writes clockInfo.txt into the cwd, so this runs from the build directory.
R=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$R/build/201"
cd "$R/build/201"
systemd-run --user --scope --quiet -p MemoryMax=4G nice -n 15 "$(python3 "$R/flow/version_pin.py" --vivado)" -mode batch -nojournal \
  -log "$R/build/201/pw.log" -source "$R/results/201_fmax_cap/pw_probe.tcl" -tclargs "$R/build/201/out" "$R/results/185_dsp_slices/rtl" "$R/results/199_dsp_fmax"
