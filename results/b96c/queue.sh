#!/usr/bin/env bash
# the 96C builds, one after the other (one Vivado at a time). 2026-11-19: rm_ctl, rm_all3 (were control, all3), ppm_ctl and ppm_all3 are the rate-matched builds from f47986f4; control is the default RATE_MATCH = 0 rebuild
cd /home/brendan/Claude_sandbox/_worktrees/96c-ppm
for v in control rm_ctl rm_all3 ppm_ctl ppm_all3; do results/b96c/build_one.sh "$v" 600; done
