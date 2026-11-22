#!/usr/bin/env bash
# xvc_board_session.sh (brief 131, NOT YET RUN ON A BOARD): the planner gives this at the board, when it is time. Pre-registration: designs/b96_kr260_10g/docs/xvc_board_test.md.
# Reads and captures only; the PL is loaded through Linux (SRAM only); never flash, eFUSE or BBRAM. Usage: xvc_board_session.sh <board ssh target> <results dir>
# The lock text must start "131:" (board job lock, _handoff/board.lock). The JTAG cable must stay unplugged from the board for the whole test (T0).
set -euo pipefail
BOARD="${1:?board ssh target}"; OUT="${2:?results dir}"
HERE="$(cd "$(dirname "$0")" && pwd)"
D="$(cd "$HERE/../.." && pwd)"
VIVADO="${VIVADO:-/opt/Xilinx/2026.1/Vivado/bin/vivado}"
LOCK=/home/brendan/Claude_sandbox/_handoff/board.lock
APP=dbg_xvc
mkdir -p "$OUT"
if ( set -o noclobber; echo "131: dbg_xvc XVC board test, $(date +%H:%M)" > "$LOCK" ) 2>/dev/null; then :; else echo "board lock held: $(cat "$LOCK")" >&2; exit 1; fi
release() { case "$(cat "$LOCK" 2>/dev/null)" in "131:"*) rm -f "$LOCK";; esac; }
trap release EXIT
# 1. on the board: the Linux heartbeat (1 Hz, whole test) and the kernel log mark; the overlay and the server are in place (docs/xvc_board_side.md, prepared by hand beforehand)
ssh "$BOARD" 'dmesg | wc -l' > "$OUT/dmesg_lines_before.txt"
ssh "$BOARD" 'nohup sh -c "while true; do date +%s.%N; sleep 1; done" > /tmp/xvc_heartbeat.log 2>&1 & echo $! > /tmp/xvc_heartbeat.pid'
ssh "$BOARD" "ps -C xvcServer_mmap -o pid= >/dev/null" || { echo "xvcServer_mmap is not running on the board" >&2; exit 1; }
# 2. from this PC: Vivado over XVC only
BOARD_HOST="${BOARD#*@}"
"$VIVADO" -mode batch -nojournal -log "$OUT/vivado_xvc.log" -source "$HERE/xvc_capture.tcl" -tclargs "${BOARD_HOST}:2542" "$D/dbg_xvc/build/base/kr260_10g_top.ltx" "$OUT/vivado_record.json"
# 3. collect, stop only the heartbeat this script started, and judge
ssh "$BOARD" 'kill $(cat /tmp/xvc_heartbeat.pid)'
ssh "$BOARD" 'cat /tmp/xvc_heartbeat.log' > "$OUT/heartbeat.log"
B=$(cat "$OUT/dmesg_lines_before.txt")
ssh "$BOARD" "dmesg | tail -n +$((B + 1))" > "$OUT/dmesg_new.txt"
python3 -I - "$OUT" <<'PY'
import json, re, sys
out = sys.argv[1]
rec = json.load(open(f"{out}/vivado_record.json"))
ts = [float(x) for x in open(f"{out}/heartbeat.log").read().split()]
rec["heartbeat_gaps_s"] = [b - a for a, b in zip(ts, ts[1:])]
rec["dmesg_new_errors"] = [l for l in open(f"{out}/dmesg_new.txt") if re.search(r"error|fail|timeout|unhandled|serror|oops|bug:", l, re.I)]
rec["jtag_cable_used"] = False      # asserted by the operator's set-up (cable unplugged); the verdict records it, nothing measures it
import csv
rows = list(csv.reader(open(f"{out}/vivado_record.json.first.csv")))
hdr = rows[0]; last = rows[-1]
pc = [i for i, h in enumerate(hdr) if h.endswith("probe0")][0]        # the 38-bit probe, shown in binary (xvc_capture.tcl), most significant bit first
bits = last[pc].strip()[::-1]                                          # bits[i] = probe bit i (docs/dbg_xvc.md)
BIT = {"pgood": 3, "mod_abs": 13, "rx_los": 14, "tx_fault": 15}
rec["static_bits"] = {k: int(bits[i]) for k, i in BIT.items()}
json.dump(rec, open(f"{out}/record.json", "w"), indent=1)
PY
python3 -I "$D/dbg_xvc/model/xvc_verdict.py" "$OUT/record.json"
