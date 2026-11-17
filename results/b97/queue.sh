#!/usr/bin/env bash
# The brief 97 Vivado queue, one heavy slot at a time (each step waits for a slot): read-only probes, then the four latency variants.
cd /home/brendan/Claude_sandbox/_worktrees/97-latency
results/b97/vivado_probes.sh 600
for v in hand_ref agent_both all3 agent_cdc; do results/b97/build_variant.sh "$v" 6 600; done
