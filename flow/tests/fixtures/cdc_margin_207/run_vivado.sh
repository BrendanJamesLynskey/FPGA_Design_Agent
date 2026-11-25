#!/usr/bin/env bash
# run_vivado.sh: the brief 207 Vivado jobs, one heavy job at a time, each in its own heavy slot.
#   run_vivado.sh <out dir> [job ...]      jobs: xpm_<fam> good_<fam> b1_<fam> b2_<fam> b3_<fam>, fam = a7 | k26
# Each job waits for load < 6 and > 12 GiB available, takes a slot through _handoff/take_heavy_slot.sh (retrying every 60 s),
# runs under systemd-run --user --scope -p MemoryMax=5G nice -n 15 (declared peak 4G: vivado_peak.py default), and releases
# only its own lock.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
flow="$(cd "$here/../../.." && pwd)"
V="${VIVADO:-$(python3 "$flow/version_pin.py" --vivado)}"
H=/home/brendan/Claude_sandbox/_handoff
out="$1"; shift; mkdir -p "$out"
jobs=("$@")
[ ${#jobs[@]} -eq 0 ] && jobs=(xpm_a7 good_a7 b1_a7 b2_a7 b3_a7 xpm_k26 good_k26 b1_k26 b2_k26 b3_k26)
A7=xc7a35ticsg324-1L; K26=xck26-sfvc784-2LV-c
GOOD="N U D_Default D_Explore D_ExtraNetDelay_high DU M_Default M_Explore M_ExtraNetDelay_high"

wait_ok() {
  while :; do
    load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
    if awk -v l="$load" 'BEGIN{exit !(l < 6)}' && [ "$avail" -gt 12 ]; then return; fi
    echo "$(date +%H:%M) waiting: load $load, avail ${avail}G"; sleep 60
  done
}
for j in "${jobs[@]}"; do
  fam=${j#*_}; part=$A7; [ "$fam" = k26 ] && part=$K26
  case "$j" in
    xpm_*)  mins=8;  cmd=(-source "$here/measure_xpm.tcl" -tclargs "$flow" "$here/rtl" "$part" "$out/xpm_$fam") ;;
    good_*) mins=45; cmd=(-source "$here/measure_vivado.tcl" -tclargs "$here/rtl" "$part" 0 6.400 "$out/vv_${fam}_good" $GOOD) ;;
    b1_*)   mins=15; cmd=(-source "$here/measure_vivado.tcl" -tclargs "$here/rtl" "$part" 1 6.400 "$out/vv_${fam}_b1" N D_Default) ;;
    b2_*)   mins=15; cmd=(-source "$here/measure_vivado.tcl" -tclargs "$here/rtl" "$part" 2 6.400 "$out/vv_${fam}_b2" N D_Default) ;;
    b3_*)   mins=25; cmd=(-source "$here/measure_vivado.tcl" -tclargs "$here/rtl" "$part" 0 2.500 "$out/vv_${fam}_b3" B3N B3U B3D_Default B3M_Default) ;;
    *) echo "unknown job $j"; continue ;;
  esac
  [ "$fam" = k26 ] && mins=$((mins * 3 / 2))
  while :; do
    wait_ok
    end=$(date -d "+$mins min" +%H:%M)
    txt="207: Vivado impl $j, $(date +%H:%M), expected end $end, peak 4G"
    envs=$("$H/take_heavy_slot.sh" --env "$txt") && break
    echo "$(date +%H:%M) slot refused for $j; retry in 60 s"; sleep 60
  done
  eval "$envs"
  echo "$(date +%H:%M) $j on $HEAVY_LOCK threads $FDA_VIVADO_THREADS"
  ( cd "$out" && FDA_FLOW="$flow" systemd-run --user --scope -q -p MemoryMax=5G nice -n 15 \
      "$V" -mode batch -nojournal -log "$out/$j.log" "${cmd[@]}" > /dev/null 2>&1 ) || echo "FAILED $j (see $out/$j.log)"
  case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "207:"*) rm -f "$HEAVY_LOCK";; esac
  echo "$(date +%H:%M) $j done"
done
