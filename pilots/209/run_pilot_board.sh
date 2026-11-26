#!/usr/bin/env bash
# Brief 209: one stage per pilot design on the KR260. THE OWNER RUNS THIS at a board visit, when the planner gives the command (the executor of brief 209
# never powered, programmed or touched the board; this script was syntax-checked and its host checks dry-run against mock buses only, pilots/209/tests).
# Each stage: checks the stamp (refuses on a mismatch), programs SRAM only, runs the host check (PASS/FAIL per criterion, pre-registered in
# pilots/209/<id>/preregistration.md), writes JSON records to results/209_kr260_pilot/hw/<timestamp>/ and leaves the board in a safe state.
#   run_pilot_board.sh <p1_clkmeter|p2_bram_rom|p3_crc_engine|p4_fir_dsp|p5_async_fifo|p6_glitchfree_mux> YES
# Hardware rules as in the b96 runs: SRAM only (flow/program.py refuses flash); the board's PL overlay is unloaded first; one board job at a time through
# board.lock (text starts "209:"); a heavy slot is held for the Vivado hardware manager. None of these designs uses a GT transmitter: the SFP+ laser stays
# off (the specs require sfp_tx_disable held at 1); the script prints that and the check leaves LEDs off. P5 soaks 10 minutes: unattended soaks need the owner's separate yes.
set -euo pipefail
STAGE="${1:?usage: run_pilot_board.sh <stage> YES}"
CONFIRM="${2:-}"
case "$STAGE" in p1_clkmeter|p2_bram_rom|p3_crc_engine|p4_fir_dsp|p5_async_fifo|p6_glitchfree_mux) ;; *) echo "unknown stage $STAGE"; exit 2;; esac
ROOT="${PILOT_ROOT:-/home/brendan/Claude_sandbox/_worktrees/209-kr260-pilot}"
H="${HANDOFF_DIR:-/home/brendan/Claude_sandbox/_handoff}"
P="$ROOT/pilots/209/$STAGE"
BOARD_RUN_FILE="$P/board_run.txt"   # the run directory the board build came from (in place: the build stamp covers the paths in build.yaml, so a copy cannot be programmed)
STAMP_FILE="$P/stamp.txt"
BOARDS="$HOME/.config/fpga_design_agent/boards.yaml"
cd "$ROOT"
[ -f "$STAMP_FILE" ] || { echo "no $STAMP_FILE: the build stamp is added after the agent's build (preregistration, Build stamp); nothing touched"; exit 2; }
EXPECT_STAMP="$(tr -d '[:space:]' < "$STAMP_FILE")"
case "$EXPECT_STAMP" in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; *) echo "stamp.txt must hold 8 hex digits, got '$EXPECT_STAMP'"; exit 2;; esac
[ -f "$BOARD_RUN_FILE" ] || { echo "no $BOARD_RUN_FILE: only designs that reached a bitstream have a board stage"; exit 2; }
DESIGN_DIR="$ROOT/$(tr -d '[:space:]' < "$BOARD_RUN_FILE")"
ls "$DESIGN_DIR"/build/base/*.bit >/dev/null 2>&1 || { echo "no bitstream in $DESIGN_DIR/build/base: the run directory in board_run.txt must still exist"; exit 2; }
GOT_STAMP="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['build_id'])" "$DESIGN_DIR/build/base/manifest.json" 2>/dev/null || echo none)"
[ "$GOT_STAMP" = "$EXPECT_STAMP" ] || { echo "build id in $DESIGN_DIR/build/base/manifest.json is $GOT_STAMP, stamp.txt says $EXPECT_STAMP: refusing; nothing touched"; exit 2; }
grep -q '^  kr260:' "$BOARDS" 2>/dev/null || { echo "no kr260 entry in $BOARDS"; exit 2; }
SERIAL="$(python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['boards']['kr260']['cable_serial'])" "$BOARDS")"
cat <<'T'
Before this starts, confirm each, in your own words:
  1. The KR260 is on its own 12 V adapter and the fan is turning; one USB cable from this PC to J4 (JTAG); nothing hot-plugged.
  2. No design in this brief uses the SFP+ transmitter. The module may stay fitted; the laser stays off (tx_disable is held at 1 by the design).
  3. You are happy for this stage to run for its stated time (P5: about 15 minutes with the soak; the others a few minutes).
T
echo "stage $STAGE, build id $GOT_STAMP"
ans="$CONFIRM"
if [ -z "$ans" ] && [ -t 0 ]; then read -r -p "Type YES to continue: " ans || true; fi
[ "$ans" = "YES" ] || { echo "not confirmed: re-run with YES as the second argument; nothing touched"; exit 3; }
if [ "${BOARD_LINUX_DOWN_OK:-}" != 1 ]; then
  ssh -o BatchMode=yes -o ConnectTimeout=10 kr260 true >/dev/null 2>&1 || { echo "board Linux not reachable: power-cycle the KR260 (boot from SD) first"; exit 6; }
fi
LOCK="$H/board.lock"; TEXT="209: $STAGE pilot board stage, $(date +%H:%M), expected end +30min"
HEAVY="$("$H/take_heavy_slot.sh" "209: $STAGE Vivado hardware manager for the board session (no implementation), $(date +%H:%M), expected end +30min")" || { echo "no heavy slot free: wait, or ask the planner"; exit 7; }
( set -o noclobber; echo "$TEXT" > "$LOCK" ) 2>/dev/null || { case "$(cat "$HEAVY" 2>/dev/null)" in "209:"*) rm -f "$HEAVY";; esac; echo "board.lock is held: $(cat "$LOCK")"; exit 4; }
release() {
  case "$(cat "$LOCK" 2>/dev/null)" in "209:"*) rm -f "$LOCK";; esac
  case "$(cat "$HEAVY" 2>/dev/null)" in "209:"*) rm -f "$HEAVY";; esac
}
trap release EXIT
if [ "${BOARD_LINUX_DOWN_OK:-}" != 1 ]; then
  echo "=== unloading the board's PL overlay (house rule: before any JTAG PL load) ==="
  if [ -z "$(ssh -o BatchMode=yes -o ConnectTimeout=10 kr260 'ls /sys/kernel/config/device-tree/overlays/ 2>/dev/null')" ]; then echo "no PL overlay loaded (already unloaded)"
  else ssh -o BatchMode=yes -o ConnectTimeout=10 kr260 'sudo -n xmutil unloadapp' || { echo "xmutil unloadapp failed: unload by hand, then re-run; nothing programmed"; exit 5; }
  fi
fi
export FDA_VIVADO_MAX="${FDA_VIVADO_MAX:-2}"
OUT="$ROOT/results/209_kr260_pilot/hw/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
git -C "$ROOT" rev-parse HEAD > "$OUT/git_head.txt"
echo "=== $STAGE: programming (SRAM only); the build id must read $EXPECT_STAMP ==="
python3 flow/program.py "$DESIGN_DIR" base --board kr260 --json "$OUT/$STAGE.program.json"
echo "=== $STAGE: host check ==="
set +e
python3 pilots/209/host/run_check.py "$STAGE" --serial "$SERIAL" --expect-build "$EXPECT_STAMP" --out "$OUT" | tee "$OUT/$STAGE.log"
RC=${PIPESTATUS[0]}
set -e
echo "RESULT $STAGE exit $RC (0 = every criterion PASS, 1 = FAIL, 3 = INCONCLUSIVE: a setup fault, repeat). Records in $OUT. SFP+ laser: not used, tx_disable held at 1 by the design. LEDs off. Locks released."
exit "$RC"
