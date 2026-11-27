#!/usr/bin/env bash
# Red Pitaya load-and-check for build 17e913f1 (rp_patgen, inside the vendor shell). Written by the agent (brief 225); RUN BY THE OWNER, AT A BOARD VISIT.
# The agent has not run this script and has not touched the board. It loads the design into the volatile PL configuration only: a power cycle, or RESTORE=1,
# returns the factory image. While the design is loaded the factory oscilloscope and generator are NOT running (the board is the target, not an instrument).
#
#   ./load_17e913f1.sh                run it (asks twice: before loading, and before anything moves OUT1)
#   RESTORE=1 ./load_17e913f1.sh      load the factory shell again (v0.94) and stop
#   DRY_RUN=1 ./...                                          print every board command instead of running it (no network, no board)
#   RP=root@<host> ./...                                     another address (default root@rp-f00c16.local)
set -u
RP="${RP:-root@rp-f00c16.local}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="${PKG:-$HERE}"
BIN="$PKG/fpga.bit.bin"
BUILD_ID=17e913f1
EXPECT_MD5=a8ee76f4336d99f7bf500c3bb2d02bed
EXPECT_BYTES=996948
REMOTE=/tmp/fda_load
DRY_RUN="${DRY_RUN:-0}"
RESTORE="${RESTORE:-0}"
OUT="${OUT:-$HERE/rp_check_$BUILD_ID.json}"
[ "$DRY_RUN" = 1 ] && OUT=/dev/stdout          # (a dry run prints; it never redirects into a file, which would cut a saved log short)

rp()  { if [ "$DRY_RUN" = 1 ]; then echo "[dry run] on $RP: $*"; else ssh -o BatchMode=yes "$RP" ". /etc/profile >/dev/null 2>&1; export PATH=/opt/redpitaya/sbin:/opt/redpitaya/bin:\$PATH; $*"; fi; }   # login environment: overlay.sh and profiles are in /opt/redpitaya/sbin and bin (board visit 2026-11-27)
put() { if [ "$DRY_RUN" = 1 ]; then echo "[dry run] copy $* to $RP:$REMOTE/"; else scp -q "$@" "$RP:$REMOTE/"; fi; }
ask() { if [ "$DRY_RUN" = 1 ]; then echo "[dry run] would ask: $1 (answered: ${DRY_ANSWER:-no})"; [ "${DRY_ANSWER:-no}" = yes ]; else printf '%s\n(type yes) > ' "$1"; read -r a; [ "$a" = yes ]; fi; }
fail() { echo "STOP: $*" >&2; exit 1; }
# check_id <block> <base> <slot>: read the block's ID register once; stop, naming the slot, if it reads 0 (nothing answers the system bus) or the wrong value
check_id() {
  if [ "$DRY_RUN" = 1 ]; then rp "cd $REMOTE && python3 redpitaya_checks.py $1 --base $2 --id-only"; return 0; fi
  idout="$(rp "cd $REMOTE && python3 redpitaya_checks.py $1 --base $2 --id-only")"; idrc=$?
  echo "$idout"
  [ "$idrc" = 0 ] && return 0
  if [ "$idrc" = 3 ]; then fail "slot $3 ($2, $1): its ID register reads 0, so the block does not answer the system bus. Nothing was written to it and no check was run. RESTORE=1 puts the factory image back."; fi
  fail "slot $3 ($2, $1): its ID register does not read $1's ID (rc $idrc): another image is loaded, or the block is wrong. Nothing was written to it. RESTORE=1 puts the factory image back."
}

if [ "$RESTORE" = 1 ]; then
  ask "Load the factory shell (v0.94) back into the board now?" || fail "not confirmed"
  rp "overlay.sh v0.94" || fail "overlay.sh v0.94 failed; power-cycle the board instead (it returns to the factory image)"
  rp "cat /sys/class/fpga_manager/fpga0/state; cat /tmp/loaded_fpga.inf"
  echo "Factory shell loaded. Set the lab file's redpitaya mode back to factory_instrument (state: factory_instrument, no build_id)."
  exit 0
fi

[ -f "$BIN" ] || fail "no $BIN"
[ "$(wc -c < "$BIN" | tr -d ' ')" = "$EXPECT_BYTES" ] || fail "$BIN is not the 996948-byte file this script was written for"
if command -v md5sum >/dev/null 2>&1; then
  [ "$(md5sum "$BIN" | cut -d' ' -f1)" = "$EXPECT_MD5" ] || fail "md5 of $BIN differs from the one this script was written for ($EXPECT_MD5)"
fi

ask "Red Pitaya $RP: the board is the owner's STEMlab 125-14 v1.1 on its 5 V 2 A supply, jumpers IN1 = LV (+-1 V) and IN2 = HV (+-20 V) as recorded, nothing above +-1 V on IN1, OUT1 into nothing that is unprotected. Loading REPLACES the factory image until a power cycle or RESTORE=1. NOTE: timing is met (WNS 0.172 ns) ONLY with the vendor's own generator and oscilloscope logic left out of the analysis by the constraints overlay: this image does not use them and they are not claimed to work. Read the results README before loading. Not a claim that the image works on the board. Load build $BUILD_ID?" || fail "not confirmed; nothing was done"

rp "mkdir -p $REMOTE" || fail "cannot reach $RP"
put "$BIN" "$PKG/redpitaya_checks.py" "$PKG/redpitaya_regs.py" "$PKG/load_fda.sh" || fail "copy failed"
rp "sh /tmp/fda_load/load_fda.sh" || fail "the load command failed: the factory image is still running or the PL is unconfigured; power-cycle to be sure"

echo "--- what the loader reports"
rp "cat /sys/class/fpga_manager/fpga0/state; cat /tmp/update_fpga.txt; cat /tmp/loaded_fpga.inf"
if [ "$DRY_RUN" != 1 ]; then
  state="$(rp "cat /sys/class/fpga_manager/fpga0/state" | tr -d '\r\n')"
  [ "$state" = operating ] || fail "fpga_manager state is '$state', not 'operating'"
  rp "grep -q '$EXPECT_MD5' /tmp/update_fpga.txt" || fail "the md5 the loader printed is not $EXPECT_MD5: another file was loaded"
  if rp "grep -qi fail /tmp/update_fpga.txt"; then fail "the loader's log /tmp/update_fpga.txt mentions a failure; read it on the board"; fi
fi

echo "--- does every user block answer the bus? (its ID register, read once)"
check_id rp_patgen 0x40600000 6
check_id rp_freqcount 0x40700000 7

echo "--- the checks (on the board, through /dev/mem, inside the block's register map only)"
DRIVE=""
if [ "rp_patgen" = rp_patgen ]; then
  if ask "DRIVES OUT1: a 0.25 V pulse train, 100 kHz, four pulses, then OUT1 returns to 0. The block cuts every level to 0.5 V. Is OUT1 connected to nothing, to a 50 ohm load or to IN1 (LV) with a short lead, and are you watching it?"; then DRIVE="--drive-ok"; fi
fi
if [ "$DRY_RUN" = 1 ]; then rp "cd $REMOTE && python3 redpitaya_checks.py rp_patgen --base 0x40600000 $DRIVE"; else rp "cd $REMOTE && python3 redpitaya_checks.py rp_patgen --base 0x40600000 $DRIVE" > "$OUT" || true; fi
echo "check record: $OUT"
if [ "$DRY_RUN" = 1 ]; then echo "[dry run] done; nothing was loaded"; exit 0; fi
python3 - "$OUT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for r in d["rows"]:
    print(r["result"].ljust(5), r["check"].ljust(22), r["detail"])
print("PASS" if d["pass"] else "FAIL")
sys.exit(0 if d["pass"] else 1)
PY
rc=$?
echo "The design stays loaded until a power cycle or RESTORE=1. Lab file: set redpitaya mode to target_loaded with build_id $BUILD_ID while it is, and back afterwards."
exit $rc
