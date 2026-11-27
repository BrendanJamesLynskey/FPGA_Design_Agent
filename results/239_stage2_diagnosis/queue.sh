#!/bin/bash
# Brief 239: the nine cells of prereg.md in the order it fixes (p1 r1, p2 r1, p3 r1, p1 r2, ...), one at a time.
for k in 1 2 3; do for d in p1_clkmeter p2_bram_rom p3_crc_engine; do
  [ -e /home/brendan/Claude_sandbox/_scratch_239/STOP ] && exit 3
  [ -e /home/brendan/Claude_sandbox/_scratch_239/done_${d}_r${k} ] && continue
  /home/brendan/Claude_sandbox/_worktrees/239-stage2/results/239_stage2_diagnosis/run_cell.sh $d $k && touch /home/brendan/Claude_sandbox/_scratch_239/done_${d}_r${k}
done; done
