#!/usr/bin/env bash
# The brief 97 Vivado queue (second attempt: the first four builds were killed at 4 minutes, exit 143, at the 6 GiB scope cap), one heavy slot at a time.
cd /home/brendan/Claude_sandbox/_worktrees/97-latency
for v in all3 hand_ref agent_both agent_cdc; do results/b97/build_variant.sh "$v" 6 600; done
