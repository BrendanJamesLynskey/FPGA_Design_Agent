#!/bin/sh
# Volatile load of /tmp/fda_load/fpga.bit.bin with the board's own v0.94 device tree overlay (build 17e913f1). It mirrors the volatile steps of
# /opt/redpitaya/sbin/overlay.sh (Red Pitaya OS 3.00), which ignores a path argument and loads /opt/<name>/fpga.bin, but takes the bitstream from /tmp.
# Nothing is written to the SD card: configfs, the PL and /tmp are all RAM. A power cycle returns the factory image.
set -u
SRC=/tmp/fda_load/fpga.bit.bin
BIN=/tmp/fda_load/fpga.bin      # the v0.94 overlay asks the FPGA manager for firmware named fpga.bin (2026-11-27: error -2 with any other name)
MODEL=$(/opt/redpitaya/bin/profiles -f) || { echo "cannot read the board model"; exit 1; }
DTBO=/opt/redpitaya/fpga/$MODEL/v0.94/fpga.dtbo
[ -f "$SRC" ] || { echo "no $SRC"; exit 1; }
cp "$SRC" "$BIN" || { echo "cannot copy to $BIN"; exit 1; }
[ -f "$DTBO" ] || { echo "no $DTBO"; exit 1; }
echo "model $MODEL, overlay $DTBO"
for f in /configfs/device-tree/overlays/*; do
  if [ -d "$f" ] && [ "$(basename "$f")" != "Led" ]; then rmdir "$f" 2>/dev/null; fi
done
rm -f /tmp/update_fpga.txt /tmp/loaded_fpga.inf
MD5SUM=$(md5sum "$BIN")
echo "Custom FPGA md5sum: $MD5SUM"
/opt/redpitaya/bin/fpgautil -b "$BIN" -o "$DTBO" -n Full > /tmp/update_fpga.txt 2>&1
STATE=$(cat /sys/class/fpga_manager/fpga0/state)
echo "fpga_manager state: $STATE"
if [ "$STATE" = "operating" ] && ! grep -q -i "fail" /tmp/update_fpga.txt; then
  echo "FPGA md5sum: $MD5SUM" >> /tmp/update_fpga.txt
  date >> /tmp/update_fpga.txt
  printf 'v0.94_fda_17e913f1' > /tmp/loaded_fpga.inf
  exit 0
fi
cat /tmp/update_fpga.txt
exit 1
