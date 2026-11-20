#!/bin/bash
# Brief 113: the bit-exactness runs. The mixed synthetic feed (rm_gp_ml/model/stream.py make_stream, seed 4242: 370 frames, 350 of them accepted by the rule path: 305 good, 22 bad or too long, 23 for another
# instrument; the others are for another port, a bad header or two messages in a frame) is injected on the receive words of the whole core in xsim 2026.1 with real XPM macros; every observed message's
# feature vector, class, decision and veto, the order count and the stage's counters are compared with the Python twin (ml_check.py). Then the board's own stream (+LOOP: the generator's frames through the
# near-end loop) against the board driver's prediction (loop_check.py). Output: results/b113/twin/*.json and the logs. usage: twin_runs.sh [work dir]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; O="$ROOT/results/b113/twin"; W="${1:-$ROOT/build/ml113_streams}"; mkdir -p "$O/logs" "$W"
cd "$ROOT"
for v in 1 0; do
  python3 -m designs.b96_kr260_10g.rm_gp_ml.model.stream "$W/s_v$v" $([ $v = 1 ] && echo veto) > "$O/stream_v$v.summary.json"
  sha256sum "$W/s_v$v/words.hex" | cut -d' ' -f1 > "$O/stream_v$v.words.sha256"
done
wait_load() { while [ "$(cut -d. -f1 /proc/loadavg)" -ge 6 ]; do sleep 20; done; }
run() {   # name build veto phase stream-dir
  wait_load
  WORK="$W/w" "$ROOT/results/b113/ml_sim.sh" "$2" "$5" "$3" "$4" 0 "$O/logs/$1.log"
}
run ml_veto_p0      ml 1 0    "$W/s_v1"; python3 results/b113/ml_check.py "$O/logs/ml_veto_p0.log"      "$W/s_v1/expect.json" "$O/ml_veto_p0.json" --veto
run ml_veto_p3100   ml 1 3100 "$W/s_v1"; python3 results/b113/ml_check.py "$O/logs/ml_veto_p3100.log"   "$W/s_v1/expect.json" "$O/ml_veto_p3100.json" --veto
run ml_shadow_p1550 ml 0 1550 "$W/s_v0"; python3 results/b113/ml_check.py "$O/logs/ml_shadow_p1550.log" "$W/s_v0/expect.json" "$O/ml_shadow_p1550.json"
run base_p1550      base 0 1550 "$W/s_v0"      # the unmodified rm_gp core on the same stream: same orders as the stage in shadow mode
for v in 1 0; do
  wait_load
  LOOP=50 WORK="$W/w" "$ROOT/results/b113/ml_sim.sh" ml "$W/s_v$v" "$v" 0 0 "$O/logs/ml_loop_v$v.log"
  python3 results/b113/loop_check.py "$O/logs/ml_loop_v$v.log" 50 "$v" "$O/ml_loop_v$v.json"
done
