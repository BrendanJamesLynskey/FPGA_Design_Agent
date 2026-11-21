#!/bin/bash
# Brief 136, scenarios 3 and 5: Lean experiments in a scratch COPY of formal/lean (the tree's Lean project is not edited).
#   bash results/b136/lean/run_lean.sh
set -e
export PATH=$HOME/.elan/bin:$PATH
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
W=$(mktemp -d)
cp -r "$ROOT/formal/lean/." "$W/"
cd "$W"
# scenario 3: the TCP checksum theorem with the payload bound 30 -> 32 (the proof text is unchanged)
sed -i 's/h : pw.length ≤ 30/h : pw.length ≤ 32/' Cksum/Spec.lean
cp "$ROOT/results/b136/lean/Probe33.lean" Cksum/Probe33.lean
cp "$ROOT/results/b136/lean/Stronger.lean" Gray/Stronger.lean
lake build Cksum Gray 2>&1 | tail -5
echo "--- scenario 3: theorem at 32 (axioms) and the RTL equations against the Internet checksum for n words of 0xFFFF, n = 0..39"
lake env lean Cksum/Probe33.lean 2>&1 | tr -d '\n' | sed 's/(\([0-9]*\), true)/\1:ok /g; s/(\([0-9]*\), false)/\1:WRONG /g'; echo
echo "--- scenario 5: gray_sample_bitwise and the two-step example"
lake build Gray.Stronger 2>&1 | grep -E "error|Build completed" || true
printf 'import Gray.Stronger\n#print axioms Gray.gray_sample_bitwise\n' > Gray/P.lean
lake env lean Gray/P.lean
