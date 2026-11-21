#!/bin/bash
# Brief 113: the latency runs. Each configuration at four phases (ps the receive clock lags the transmit clock) on the same latency stream (rm_gp_ml/model/stream.py make_lat_stream).
#   usage: lat_all.sh <stream dir> <out dir>
# Waits while the machine load is 6 or more (simulation-only runs need no heavy slot only under that load, house rules). Configurations: base (unmodified rm_gp), ml shadow (veto 0),
# ml veto (veto 1), and the counterfactual ML_HOLD 1 and 2 (veto 1): what the stage would cost if the class were made after the message arrived.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; S="$1"; O="$2"; mkdir -p "$O"
for cfg in "base 0 0" "ml 0 0" "ml 1 0" "ml 1 1" "ml 1 2"; do
  set -- $cfg
  for ph in 0 1550 3100 4650; do
    f="$O/${1}_v${2}_h${3}_p${ph}.log"
    [ -s "$f" ] && continue
    while [ "$(cut -d. -f1 /proc/loadavg)" -ge 6 ]; do sleep 20; done
    "$ROOT/results/b113/ml_sim.sh" "$1" "$S" "$2" "$ph" "$3" "$f"
  done
done
