#!/usr/bin/env bash
# the three 97C rebuilds, one after the other (one Vivado at a time)
cd /home/brendan/Claude_sandbox/_worktrees/97c-seq
for v in control agent_both all3; do results/b97c/build_one.sh "$v" 600; done
