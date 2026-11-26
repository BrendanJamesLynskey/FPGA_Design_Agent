#!/bin/bash
# Runs every group on both parts, one slot per group (run_dsp.py takes and releases the slot). VU2P is not run: the licence refuses it (brief 186 licence.md).
cd "$(dirname "$0")/../.."
for p in a7 k26; do for g in mul dot feat wide; do python3 results/185_dsp_slices/run_dsp.py run --part $p --group $g; done; done
echo ALLDONE
