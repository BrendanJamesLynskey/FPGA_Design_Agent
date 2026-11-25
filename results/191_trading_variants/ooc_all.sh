#!/bin/bash
# Brief 191: out-of-context place-and-route on the K26 (xck26-sfvc784-2LV-c, Vivado 2026.1) in one heavy slot, one Vivado session at a time:
#   itch_dec alone, shift versus in-place, at 6.2061 / 3.6 / 3.0 ns (the logic depth and the clock the decoder alone reaches);
#   itch_ouch_top at 6.2061 ns: the base (PARSE_INPLACE 0, DUAL_FEED 0), PARSE_INPLACE 1, and DUAL_FEED 1 (feed_arb in front).
# Run from the worktree root:  results/191_trading_variants/ooc_all.sh
set -u
H=/home/brendan/Claude_sandbox/_handoff
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
TEXT="191: itch_dec + itch_ouch_top OOC variants (9 Vivado runs, one at a time), $(date +%H:%M), expected end $(date -d '+70 min' +%H:%M), peak 4G"
LOCK=""
until LOCK=$("$H/take_heavy_slot.sh" "$TEXT" 2>/dev/null); do sleep 60; done
echo "slot: $LOCK at $(date +%H:%M)"
for ip in 0 1; do
  python3 -m designs.b110_itch_ouch.ooc.ooc --dut dec --tag dec_ip$ip --param PARSE_INPLACE=$ip --clocks 6.2061 3.6 3.0 --out results/191_trading_variants/ooc
done
python3 -m designs.b110_itch_ouch.ooc.ooc --tag top_base --param N_INST=4 --clocks 6.2061 --out results/191_trading_variants/ooc
python3 -m designs.b110_itch_ouch.ooc.ooc --tag top_inplace --param N_INST=4 PARSE_INPLACE=1 --clocks 6.2061 --out results/191_trading_variants/ooc
python3 -m designs.b110_itch_ouch.ooc.ooc --tag top_dual --param N_INST=4 DUAL_FEED=1 --clocks 6.2061 --out results/191_trading_variants/ooc
case "$(cat "$LOCK")" in "191:"*) rm "$LOCK";; esac
echo "done at $(date +%H:%M)"
