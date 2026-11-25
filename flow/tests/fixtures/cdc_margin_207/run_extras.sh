#!/usr/bin/env bash
# run_extras.sh: brief 207 follow-up Vivado runs, one heavy job at a time, each in its own slot:
#   analysis_<fam>: measure_analysis.tcl on the good design's synth.dcp (E1-E3 as analysis-only effects on ONE routed design)
#   xpm_fixed_<fam>: measure_xpm.tcl again after the flow/xpm_cdc.tcl handshake fix (before/after evidence)
#   run_extras.sh <out dir>
set -u
here="$(cd "$(dirname "$0")" && pwd)"; flow="$(cd "$here/../../.." && pwd)"
V="${VIVADO:-$(python3 "$flow/version_pin.py" --vivado)}"; H=/home/brendan/Claude_sandbox/_handoff
out="$1"
for j in analysis_a7 analysis_k26 xpm_fixed_a7 xpm_fixed_k26; do
  fam=${j##*_}; part=xc7a35ticsg324-1L; [ "$fam" = k26 ] && part=xck26-sfvc784-2LV-c
  case "$j" in
    analysis_*) cmd=(-source "$here/measure_analysis.tcl" -tclargs "$out/vv_${fam}_good" "$part" "$out/$j") ;;
    xpm_fixed_*) cmd=(-source "$here/measure_xpm.tcl" -tclargs "$flow" "$here/rtl" "$part" "$out/$j") ;;
  esac
  while :; do
    load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
    if awk -v l="$load" 'BEGIN{exit !(l < 6)}' && [ "$avail" -gt 12 ]; then
      envs=$("$H/take_heavy_slot.sh" --env "207: Vivado impl $j, $(date +%H:%M), expected end $(date -d '+15 min' +%H:%M), peak 4G") && break
    fi
    sleep 60
  done
  eval "$envs"; echo "$(date +%H:%M) $j on $HEAVY_LOCK threads $FDA_VIVADO_THREADS"
  ( cd "$out" && systemd-run --user --scope -q -p MemoryMax=5G nice -n 15 "$V" -mode batch -nojournal -log "$out/$j.log" "${cmd[@]}" \
      > /dev/null 2>&1 ) || echo "FAILED $j"
  case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "207:"*) rm -f "$HEAVY_LOCK";; esac
  echo "$(date +%H:%M) $j done"
done
