#!/usr/bin/env bash
# the four 96C builds, one after the other (one Vivado at a time)
cd /home/brendan/Claude_sandbox/_worktrees/96c-ppm
for v in control all3 ppm_ctl ppm_all3; do results/b96c/build_one.sh "$v" 600; done
