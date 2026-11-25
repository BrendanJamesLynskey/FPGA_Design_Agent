#!/usr/bin/env bash
# run_quartus.sh: the brief 207 Quartus Prime Lite jobs, one compile at a time, each in its own heavy slot.
#   run_quartus.sh <out dir> [fam ...]        fam = cv (Cyclone V 5CSEMA5F31C6) | m10 (MAX 10 10M50DAF484C7G)
# Per family, fits (design, fit variant, seed) and the analysis variants run on each fit:
#   good N 1 -> N ; good U 1 -> U ; good D 1/2/3 -> N U D DU ; b1 D 1 -> N D ; b2 D 1 -> N D
# Each fit waits for load < 6 and > 12 GiB available, takes a slot (_handoff/take_heavy_slot.sh, peak 2G), runs under
# systemd-run --user --scope -p MemoryMax=3G nice -n 15, and releases only its own lock.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
Q=/home/brendan/altera_lite/25.1std/quartus/bin
H=/home/brendan/Claude_sandbox/_handoff
out="$1"; shift; mkdir -p "$out"
fams=("$@"); [ ${#fams[@]} -eq 0 ] && fams=(cv m10)
wait_ok() {
  while :; do
    load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
    if awk -v l="$load" 'BEGIN{exit !(l < 6)}' && [ "$avail" -gt 12 ]; then return; fi
    echo "$(date +%H:%M) waiting: load $load, avail ${avail}G"; sleep 60
  done
}
run_fit() {  # fam family device design bad fitvar seed anavars...
  local fam=$1 family=$2 device=$3 des=$4 bad=$5 fv=$6 seed=$7; shift 7
  local w="$out/q_${fam}_${des}_${fv}_s${seed}"
  while :; do
    wait_ok
    txt="207: Quartus fit $fam $des $fv s$seed, $(date +%H:%M), expected end $(date -d '+8 min' +%H:%M), peak 2G, no Vivado"
    lock=$("$H/take_heavy_slot.sh" "$txt") && break
    echo "$(date +%H:%M) slot refused; retry in 60 s"; sleep 60
  done
  echo "$(date +%H:%M) $w on $lock"
  ( Q207_VARIANT=$fv Q207_PB=6.400 systemd-run --user --scope -q -p MemoryMax=3G nice -n 15 \
      "$Q/quartus_sh" -t "$here/q_build.tcl" "$here/rtl" "$w/proj" "$family" "$device" "$bad" "$here/q_variant.sdc" "$seed" \
      > "$w.build.log" 2>&1 ) || echo "FAILED build $w"
  ( systemd-run --user --scope -q -p MemoryMax=3G nice -n 15 \
      "$Q/quartus_sta" -t "$here/q_sta.tcl" "$w/proj" "$here/q_variant.sdc" "$w" 6.400 "$@" > "$w.sta.log" 2>&1 ) || echo "FAILED sta $w"
  case "$(cat "$lock" 2>/dev/null)" in "207:"*) rm -f "$lock";; esac
  echo "$(date +%H:%M) $w done"
}
for f in "${fams[@]}"; do
  case "$f" in
    cv)  fam="Cyclone V"; dev=5CSEMA5F31C6 ;;
    m10) fam="MAX 10";    dev=10M50DAF484C7G ;;
    *) echo "unknown $f"; continue ;;
  esac
  run_fit $f "$fam" $dev good 0 D 1 N U D DU DD
  run_fit $f "$fam" $dev good 0 N 1 N
  run_fit $f "$fam" $dev good 0 U 1 U
  run_fit $f "$fam" $dev good 0 D 2 D
  run_fit $f "$fam" $dev good 0 D 3 D
  run_fit $f "$fam" $dev b1 1 D 1 N D
  run_fit $f "$fam" $dev b2 2 D 1 N D
done
