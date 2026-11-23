#!/bin/bash
# Brief 191: out-of-context place-and-route of itch_dec alone (K26, Vivado 2026.1), both parse variants, three clocks each, one heavy slot.
# Run from the worktree root:  results/191_trading_variants/ooc_dec.sh <TAG_SUFFIX>
set -u
H=/home/brendan/Claude_sandbox/_handoff
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
TEXT="191: itch_dec OOC shift vs in-place, 3 clocks each, $(date +%H:%M), expected end $(date -d '+50 min' +%H:%M), peak 2G"
LOCK=""
until LOCK=$("$H/take_heavy_slot.sh" "$TEXT" 2>/dev/null); do sleep 90; done
echo "slot: $LOCK"
for ip in 0 1; do
  tag=dec_${1:-run}_ip$ip
  python3 -m designs.b110_itch_ouch.ooc.ooc --dut dec --tag "$tag" --param PARSE_INPLACE=$ip --clocks 6.2061 3.6 3.0 --out results/191_trading_variants/ooc
done
case "$(cat "$LOCK")" in "191:"*) rm "$LOCK";; esac
echo done
