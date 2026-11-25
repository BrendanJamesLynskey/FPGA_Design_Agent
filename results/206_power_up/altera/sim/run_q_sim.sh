#!/bin/bash
# Brief 206 Q10: Icarus functional simulation of each compiled case's post-fit netlist (sim-only, small).
# Usage: run_q_sim.sh <build/q> > records/altera_gate_sim.txt
set -u
here=$(cd "$(dirname "$0")" && pwd); b=$1
L=/home/brendan/altera_lite/25.1std/quartus/eda/sim_lib
declare -A ATOMS=([c4]=cycloneive_atoms.v [m10]=fiftyfivenm_atoms.v [c5]=cyclonev_atoms.v)
for c in "$b"/q_*_pbON "$b"/q_*_pbOFF; do
  [ -d "$c" ] || continue
  n=$(basename "$c"); tag=$(echo "$n" | sed -E 's/q_([a-z0-9]+)_i.*/\1/')
  vo=$(ls "$c"/simulation/questa/*85c_slow.vo 2>/dev/null | head -1); [ -n "$vo" ] || vo=$(ls "$c"/simulation/questa/*.vo 2>/dev/null | head -1)
  echo "== $n ($(basename "$vo"), $(basename ${ATOMS[$tag]}))"
  [ -n "$vo" ] || { echo "no netlist"; continue; }
  w=$(mktemp -d "$b/sim_XXXX")
  if iverilog -g2012 -s tb -s glbl -o "$w/a.out" "$here/tb_q.v" "$here/glbl_stub.v" "$here/encrypted_stubs.v" "$L/altera_primitives.v" "$L/${ATOMS[$tag]}" "$vo" > "$w/iv.log" 2>&1; then
    vvp -n "$w/a.out" | command grep -E '^(POWERUP|ASYNC|SYNC|AFTER)'
  else
    echo "iverilog failed: $(head -3 "$w/iv.log" | tr '\n' ' ')"
  fi
done
