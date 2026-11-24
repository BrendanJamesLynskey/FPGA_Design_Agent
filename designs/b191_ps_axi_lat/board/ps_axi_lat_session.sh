#!/usr/bin/env bash
# ps_axi_lat_session.sh (brief 191, board row B-R8, NOT YET RUN ON A BOARD): the planner gives this at the board, when it is time. Pre-registration: docs/ps_axi_lat.md and
# _handoff/fpga_agent/next_board_visit_plan.md row B-R8. The PL image is loaded through Linux (SRAM only); never flash, eFUSE or BBRAM; nothing outside the probes' two 4 KiB windows is touched.
# Usage: ps_axi_lat_session.sh <board ssh target> <results dir> <built bitstream (.bit)> <expected build stamp>
# Needs on this PC: bootgen (Vivado 2026.1), dtc, the aarch64 cross compiler (aarch64-linux-gnu-gcc). Needs on the board: nothing installed (the program is a static binary).
# The lock text must start "191:" (board job lock, _handoff/board.lock). Runs the whole session three times in a row (each run is --runs 5 of --n 200000 per figure).
set -euo pipefail
BOARD="${1:?board ssh target}"; OUT="${2:?results dir}"; BIT="${3:?bitstream .bit}"; EXPECT="${4:?expected build id, the stamp the build printed, 0x then 8 hex digits}"
HERE="$(cd "$(dirname "$0")" && pwd)"
D="$(cd "$HERE/.." && pwd)"
LOCK=/home/brendan/Claude_sandbox/_handoff/board.lock
APP=ps_axi_lat
mkdir -p "$OUT"
if ( set -o noclobber; echo "191: ps_axi_lat board test, $(date +%H:%M)" > "$LOCK" ) 2>/dev/null; then :; else echo "board lock held: $(cat "$LOCK")" >&2; exit 1; fi
release() { case "$(cat "$LOCK" 2>/dev/null)" in "191:"*) rm -f "$LOCK";; esac; }
trap release EXIT
# 1. on this PC: the program, the app files
aarch64-linux-gnu-gcc -O2 -Wall -static -o "$OUT/ps_axi_lat" "$D/host/ps_axi_lat.c"
sha256sum "$OUT/ps_axi_lat" "$BIT" > "$OUT/sha256.txt"
printf 'all:\n{\n\t%s\n}\n' "$BIT" > "$OUT/$APP.bif"
bootgen -arch zynqmp -image "$OUT/$APP.bif" -o "$OUT/$APP.bit.bin" -w on
dtc -@ -I dts -O dtb -o "$OUT/$APP.dtbo" "$D/board/pl-ps-axi-lat.dtsi"
# 2. on the board: the app directory, the load (xmutil), the run, the unload. Operating conditions are read before and after (temperature, supplies, CPU frequency and governor).
ssh "$BOARD" "mkdir -p /tmp/$APP"
scp -q "$OUT/ps_axi_lat" "$OUT/$APP.bit.bin" "$OUT/$APP.dtbo" "$D/board/shell.json" "$BOARD:/tmp/$APP/"
ssh "$BOARD" "sudo mkdir -p /lib/firmware/xilinx/$APP && sudo cp /tmp/$APP/$APP.bit.bin /tmp/$APP/$APP.dtbo /tmp/$APP/shell.json /lib/firmware/xilinx/$APP/ && sudo xmutil unloadapp; sudo xmutil loadapp $APP"
ssh "$BOARD" 'uname -a; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq; cat /sys/class/thermal/thermal_zone*/temp; dmesg | tail -n 5' > "$OUT/conditions_before.txt" 2>&1 || true
for run in 1 2 3; do
  for port in "fpd 0xA0000000" "lpd 0x80000000"; do
    set -- $port
    ssh "$BOARD" "sudo /tmp/$APP/ps_axi_lat --base $2 --label $1 --cpu 2 --n 200000 --runs 5 --expect-build $EXPECT" > "$OUT/result_${1}_run${run}.json"
  done
done
ssh "$BOARD" 'cat /sys/class/thermal/thermal_zone*/temp; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq; dmesg | tail -n 20' > "$OUT/conditions_after.txt" 2>&1 || true
ssh "$BOARD" "sudo xmutil unloadapp; rm -rf /tmp/$APP"
python3 -I "$D/scripts/ps_axi_lat_verdict.py" "$OUT"
