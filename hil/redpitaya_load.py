"""The Red Pitaya load-and-check script, written for the owner to run at a board visit, and its dry run (brief 225).

    python3 -m hil.redpitaya_load script <package-dir> --block rp_freqcount [--expect-hz 1000000] [--bare] [-o load_<build>.sh]
    python3 -m hil.redpitaya_load dry-run --block rp_freqcount [--freq 1000000]       # the checks against a model, and the script's own DRY_RUN=1 path

``<package-dir>`` holds ``fpga.bit.bin`` and ``build.json`` (``tools/rp_shell.py package``). The script it writes:

* loads the design into the **volatile** PL configuration only, from ``/tmp`` on the board, so nothing is written to the SD card by the load itself and a power
  cycle returns the factory image. Shell builds (which keep the shell's own device tree) are loaded by the generated ``load_fda.sh`` (brief 243, from the board
  visit of 2026-11-27: OS 3.00's ``overlay.sh <name> <path>`` ignores the path and loads ``/opt/<name>/fpga.bin``, and the v0.94 device tree asks the kernel for
  firmware named ``fpga.bin``, so the script does by hand what ``overlay.sh`` does, with the file in ``/tmp``); bare builds use ``fpgautil``;
* runs every board command in a login-like environment (``/etc/profile``, ``/opt/redpitaya/sbin`` and ``/opt/redpitaya/bin`` on PATH): a non-interactive ssh
  session has neither;
* verifies the load from the files the loader itself writes (``/sys/class/fpga_manager/fpga0/state`` must be ``operating``, ``/tmp/update_fpga.txt`` holds the md5 of
  the loaded file and no ``fail``, ``/tmp/loaded_fpga.inf``), then reads the ID register of every user block in the image and **stops, naming the slot, if one
  reads 0 or the wrong value** (a block that does not answer the bus: build 170300fd read 0 in both slots), and only then runs ``hil/redpitaya_checks.py`` on the
  board and brings the JSON back;
* asks the owner to type ``yes`` before it loads (the board is the owner's, the jumpers are as recorded, nothing above 1 V is on IN1), and again before a check
  that moves OUT1;
* never touches the SD card's boot partition or boot files, the OS image or updater, or the factory SCPI server (``agent.core.permissions.check_script`` is
  run over the text, and the tests refuse a script that fails it);
* restores the factory image on request (``RESTORE=1``): ``overlay.sh v0.94`` loads the factory shell again; a power cycle does the same.

Nothing here connects to a board. The agent writes the script and dry-runs it (``DRY_RUN=1``: every board command is printed, none is run, the confirmations
are answered by a variable); the owner runs the real one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path

from hil import redpitaya_checks as C
from hil import redpitaya_models as M
from hil.redpitaya_regs import MAPS, SLOT_BASES, MockWindow

HOST = "rp-f00c16.local"                  # the owner's board (record of 2026-11-25); the script takes RP=<user@host> to override
FACTORY_FPGA = "v0.94"                    # the factory shell's name for overlay.sh (Red Pitaya OS 3.00 lists v0.94 among its standard images)
REMOTE_DIR = "/tmp/fda_load"
STATE_FILES = ("/sys/class/fpga_manager/fpga0/state", "/tmp/update_fpga.txt", "/tmp/loaded_fpga.inf")


def md5(p: Path) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()           # the loader prints an md5 of the loaded file; it is a check of the copy, not of security


RP_ENV = ". /etc/profile >/dev/null 2>&1; export PATH=/opt/redpitaya/sbin:/opt/redpitaya/bin:\\$PATH"      # what a login shell has and a non-interactive ssh command lacks


def render_load_fda(build_id: str) -> str:
    """``load_fda.sh``, run on the board: the volatile load of ``/tmp/fda_load/fpga.bit.bin`` with the board's own v0.94 device-tree overlay (brief 243). It mirrors
    the volatile steps of Red Pitaya OS 3.00's ``overlay.sh`` and takes the bitstream from /tmp. Nothing is written to the SD card."""
    return f"""#!/bin/sh
# Volatile load of {REMOTE_DIR}/fpga.bit.bin with the board's own {FACTORY_FPGA} device tree overlay (build {build_id}). It mirrors the volatile steps of
# /opt/redpitaya/sbin/overlay.sh (Red Pitaya OS 3.00), which ignores a path argument and loads /opt/<name>/fpga.bin, but takes the bitstream from /tmp.
# Nothing is written to the SD card: configfs, the PL and /tmp are all RAM. A power cycle returns the factory image.
set -u
SRC={REMOTE_DIR}/fpga.bit.bin
BIN={REMOTE_DIR}/fpga.bin      # the {FACTORY_FPGA} overlay asks the FPGA manager for firmware named fpga.bin (2026-11-27: error -2 with any other name)
MODEL=$(/opt/redpitaya/bin/profiles -f) || {{ echo "cannot read the board model"; exit 1; }}
DTBO=/opt/redpitaya/fpga/$MODEL/{FACTORY_FPGA}/fpga.dtbo
[ -f "$SRC" ] || {{ echo "no $SRC"; exit 1; }}
cp "$SRC" "$BIN" || {{ echo "cannot copy to $BIN"; exit 1; }}
[ -f "$DTBO" ] || {{ echo "no $DTBO"; exit 1; }}
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
  printf '{FACTORY_FPGA}_fda_{build_id}' > /tmp/loaded_fpga.inf
  exit 0
fi
cat /tmp/update_fpga.txt
exit 1
"""


def render_script(package: Path, block: str, *, expect_hz: float | None = None, bare: bool = False, slot: int = 7, also: tuple[tuple[str, int], ...] = ()) -> str:
    """The owner's script for the package in ``package`` (``fpga.bit.bin`` and ``build.json``). ``also``: the other blocks in the same image, as (block, slot):
    their ID registers are read after the load too."""
    info = json.loads((Path(package) / "build.json").read_text())
    binf = Path(package) / "fpga.bit.bin"
    build_id, size = info["build_id"], binf.stat().st_size
    load = (f'rp "fpgautil -b {REMOTE_DIR}/fpga.bit.bin -f Full"' if bare else f'rp "sh {REMOTE_DIR}/load_fda.sh"')
    id_calls = "\n".join(f"check_id {b} {SLOT_BASES[sl]:#x} {sl}" for b, sl in ((block, slot),) + tuple(also))
    expect = (f" --expect-hz {expect_hz!r}" if expect_hz else "") + (f" --base {SLOT_BASES[slot]:#x}" if slot != 7 else "")
    t = info.get("timing") or {}
    warn = ""
    if t.get("timing_met") and info.get("overlay"):
        warn = (f" NOTE: timing is met (WNS {t.get('wns_ns')} ns) ONLY with the vendor's own generator and oscilloscope logic left out of the analysis by the constraints overlay: "
                "this image does not use them and they are not claimed to work. Read the results README before loading. Not a claim that the image works on the board.")
    if t.get("timing_met") is False:
        warn = (f" NOTE: this build's timing is NOT met (WNS {t.get('wns_ns')} ns, {t.get('tns_failing_endpoints')} failing endpoints; see build.json). "
                + ("Read the results README before loading: the vendor's own generator and oscilloscope logic is left out of this build's timing by the constraints overlay "
                   "(this image does not use them; they are not claimed to work), so the figure above is for the shell's bus, the ADC and DAC front end and the blocks: "
                   "the misses are in the blocks, by tenths of a nanosecond at the slow corner. Not a claim that the image works." if info.get("overlay") else
                   "Read the results README before loading: the failing paths measured so far are in the vendor's own generator FIFO, not in the user block."))
    return f"""#!/usr/bin/env bash
# Red Pitaya load-and-check for build {build_id} ({block}, {"bare" if bare else "inside the vendor shell"}). Written by the agent (brief 225); RUN BY THE OWNER, AT A BOARD VISIT.
# The agent has not run this script and has not touched the board. It loads the design into the volatile PL configuration only: a power cycle, or RESTORE=1,
# returns the factory image. While the design is loaded the factory oscilloscope and generator are NOT running (the board is the target, not an instrument).
#
#   ./{Path("load_" + build_id + ".sh").name}                run it (asks twice: before loading, and before anything moves OUT1)
#   RESTORE=1 ./{Path("load_" + build_id + ".sh").name}      load the factory shell again ({FACTORY_FPGA}) and stop
#   DRY_RUN=1 ./...                                          print every board command instead of running it (no network, no board)
#   RP=root@<host> ./...                                     another address (default root@{HOST})
set -u
RP="${{RP:-root@{HOST}}}"
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PKG="${{PKG:-$HERE}}"
BIN="$PKG/fpga.bit.bin"
BUILD_ID={build_id}
EXPECT_MD5={md5(binf)}
EXPECT_BYTES={size}
REMOTE={REMOTE_DIR}
DRY_RUN="${{DRY_RUN:-0}}"
RESTORE="${{RESTORE:-0}}"
OUT="${{OUT:-$HERE/rp_check_$BUILD_ID.json}}"
[ "$DRY_RUN" = 1 ] && OUT=/dev/stdout          # (a dry run prints; it never redirects into a file, which would cut a saved log short)

rp()  {{ if [ "$DRY_RUN" = 1 ]; then echo "[dry run] on $RP: $*"; else ssh -o BatchMode=yes "$RP" "{RP_ENV}; $*"; fi; }}   # login environment: overlay.sh and profiles are in /opt/redpitaya/sbin and bin (board visit 2026-11-27)
put() {{ if [ "$DRY_RUN" = 1 ]; then echo "[dry run] copy $* to $RP:$REMOTE/"; else scp -q "$@" "$RP:$REMOTE/"; fi; }}
ask() {{ if [ "$DRY_RUN" = 1 ]; then echo "[dry run] would ask: $1 (answered: ${{DRY_ANSWER:-no}})"; [ "${{DRY_ANSWER:-no}}" = yes ]; else printf '%s\\n(type yes) > ' "$1"; read -r a; [ "$a" = yes ]; fi; }}
fail() {{ echo "STOP: $*" >&2; exit 1; }}
# check_id <block> <base> <slot>: read the block's ID register once; stop, naming the slot, if it reads 0 (nothing answers the system bus) or the wrong value
check_id() {{
  if [ "$DRY_RUN" = 1 ]; then rp "cd $REMOTE && python3 redpitaya_checks.py $1 --base $2 --id-only"; return 0; fi
  idout="$(rp "cd $REMOTE && python3 redpitaya_checks.py $1 --base $2 --id-only")"; idrc=$?
  echo "$idout"
  [ "$idrc" = 0 ] && return 0
  if [ "$idrc" = 3 ]; then fail "slot $3 ($2, $1): its ID register reads 0, so the block does not answer the system bus. Nothing was written to it and no check was run. RESTORE=1 puts the factory image back."; fi
  fail "slot $3 ($2, $1): its ID register does not read $1's ID (rc $idrc): another image is loaded, or the block is wrong. Nothing was written to it. RESTORE=1 puts the factory image back."
}}

if [ "$RESTORE" = 1 ]; then
  ask "Load the factory shell ({FACTORY_FPGA}) back into the board now?" || fail "not confirmed"
  rp "overlay.sh {FACTORY_FPGA}" || fail "overlay.sh {FACTORY_FPGA} failed; power-cycle the board instead (it returns to the factory image)"
  rp "cat /sys/class/fpga_manager/fpga0/state; cat /tmp/loaded_fpga.inf"
  echo "Factory shell loaded. Set the lab file's redpitaya mode back to factory_instrument (state: factory_instrument, no build_id)."
  exit 0
fi

[ -f "$BIN" ] || fail "no $BIN"
[ "$(wc -c < "$BIN" | tr -d ' ')" = "$EXPECT_BYTES" ] || fail "$BIN is not the {size}-byte file this script was written for"
if command -v md5sum >/dev/null 2>&1; then
  [ "$(md5sum "$BIN" | cut -d' ' -f1)" = "$EXPECT_MD5" ] || fail "md5 of $BIN differs from the one this script was written for ($EXPECT_MD5)"
fi

ask "Red Pitaya $RP: the board is the owner's STEMlab 125-14 v1.1 on its 5 V 2 A supply, jumpers IN1 = LV (+-1 V) and IN2 = HV (+-20 V) as recorded, nothing above +-1 V on IN1, OUT1 into nothing that is unprotected. Loading REPLACES the factory image until a power cycle or RESTORE=1.{warn} Load build $BUILD_ID?" || fail "not confirmed; nothing was done"

rp "mkdir -p $REMOTE" || fail "cannot reach $RP"
put "$BIN" "$PKG/redpitaya_checks.py" "$PKG/redpitaya_regs.py"{"" if bare else ' "$PKG/load_fda.sh"'} || fail "copy failed"
{load} || fail "the load command failed: the factory image is still running or the PL is unconfigured; power-cycle to be sure"

echo "--- what the loader reports"
rp "cat {STATE_FILES[0]}; cat {STATE_FILES[1]}; cat {STATE_FILES[2]}"
if [ "$DRY_RUN" != 1 ]; then
  state="$(rp "cat {STATE_FILES[0]}" | tr -d '\\r\\n')"
  [ "$state" = operating ] || fail "fpga_manager state is '$state', not 'operating'"
  rp "grep -q '$EXPECT_MD5' /tmp/update_fpga.txt" || fail "the md5 the loader printed is not $EXPECT_MD5: another file was loaded"
  if rp "grep -qi fail /tmp/update_fpga.txt"; then fail "the loader's log /tmp/update_fpga.txt mentions a failure; read it on the board"; fi
fi

echo "--- does every user block answer the bus? (its ID register, read once)"
{id_calls}

echo "--- the checks (on the board, through /dev/mem, inside the block's register map only)"
DRIVE=""
if [ "{block}" = rp_patgen ]; then
  if ask "DRIVES OUT1: a 0.25 V pulse train, 100 kHz, four pulses, then OUT1 returns to 0. The block cuts every level to 0.5 V. Is OUT1 connected to nothing, to a 50 ohm load or to IN1 (LV) with a short lead, and are you watching it?"; then DRIVE="--drive-ok"; fi
fi
if [ "$DRY_RUN" = 1 ]; then rp "cd $REMOTE && python3 redpitaya_checks.py {block}{expect} $DRIVE"; else rp "cd $REMOTE && python3 redpitaya_checks.py {block}{expect} $DRIVE" > "$OUT" || true; fi
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
"""


def dry_run(block: str, freq_hz: float | None = 1_000_000.0, drive_ok: bool = False) -> dict:
    """The checks against the model of ``block`` (a mock window): the dry run of the board-side half. Marked ``mock``; never evidence."""
    if block == "rp_freqcount":
        model = M.FreqCountModel(M.SineSignal(freq_hz or 1e6, amp=4000.0, offset=0.0, phase0=0.3))
        win = MockWindow(model)
        rows = C.run_block(block, win, freq_hz, tol_ppm=1000.0, sleep=lambda _s: None)
    else:
        model = M.PatGenModel()
        win = MockWindow(model)
        rows = C.run_block(block, win, None, drive_ok=drive_ok, sleep=lambda _s: None)
    return {"schema": "fpga-design-agent/rp-check/v1", "block": block, "mock": True, "evidence": False, "rows": rows, "accesses": len(win.log),
            "pass": all(r["result"] == "pass" for r in rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("script")
    s.add_argument("package", type=Path)
    s.add_argument("--block", choices=sorted(MAPS), required=True)
    s.add_argument("--expect-hz", type=float)
    s.add_argument("--bare", action="store_true")
    s.add_argument("--slot", type=int, choices=sorted(SLOT_BASES), default=7, help="the shell slot the block is in (7: 0x40700000, 6: 0x40600000)")
    s.add_argument("--also", action="append", default=[], metavar="BLOCK:SLOT", help="another block in the same image (e.g. rp_patgen:6): its ID register is read after the load too")
    s.add_argument("-o", "--out", type=Path)
    d = sub.add_parser("dry-run")
    d.add_argument("--block", choices=sorted(MAPS), required=True)
    d.add_argument("--freq", type=float, default=1_000_000.0)
    d.add_argument("--drive-ok", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "script":
        from agent.core import permissions as P
        also = tuple((x.split(":")[0], int(x.split(":")[1])) for x in a.also)
        text = render_script(a.package, a.block, expect_hz=a.expect_hz, bare=a.bare, slot=a.slot, also=also)
        build_id = json.loads((Path(a.package) / "build.json").read_text())["build_id"]
        loader = render_load_fda(build_id)
        for t in (text, loader):
            bad = P.check_script(t)
            if bad:
                print("refused: the script breaks the never-list:", bad, file=sys.stderr)
                return 2
        if not a.bare:
            (Path(a.package) / "load_fda.sh").write_text(loader)
        for f in ("redpitaya_checks.py", "redpitaya_regs.py"):          # the files the script copies to the board beside the bitstream
            (Path(a.package) / f).write_text((Path(__file__).parent / f).read_text())
        out = a.out or Path(a.package) / f"load_{json.loads((Path(a.package) / 'build.json').read_text())['build_id']}.sh"
        out.write_text(text)
        out.chmod(0o755)
        print(out)
        return 0
    r = dry_run(a.block, a.freq, a.drive_ok)
    print(json.dumps(r, indent=1))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
