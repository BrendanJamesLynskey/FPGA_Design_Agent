#!/bin/bash
cd /home/brendan/Claude_sandbox/_worktrees/185-dsp-slices
for p in a7 k26; do for g in mul dot feat wide; do python3 results/185_dsp_slices/run_dsp.py run --part $p --group $g; done; done
echo ALLDONE
