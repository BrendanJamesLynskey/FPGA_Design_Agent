#!/bin/bash
# Brief 199: re-run the pulse-width probe (five routed out-of-context runs, one thread). Takes a heavy slot first:
#   _handoff/take_heavy_slot.sh "199: Vivado impl OOC 5 small DSP pulse-width probe runs, <start>, expected end <hh:mm>, peak 3G"
R=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$R/build/199"
systemd-run --user --scope --quiet -p MemoryMax=5G nice -n 15 "$(python3 "$R/flow/version_pin.py" --vivado)" -mode batch -nojournal \
  -log "$R/build/199/pw.log" -source "$R/results/199_dsp_fmax/pw_probe.tcl" -tclargs "$R/build/199" "$R/results/185_dsp_slices/rtl" "$R/results/199_dsp_fmax"
