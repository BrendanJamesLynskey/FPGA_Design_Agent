# Earlier board attempts

The board plan ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml)) lists every run and the verdict each must give. It
was written before the board was first used and has not changed since. The plan was run on three builds of the design.
The result is the last run, [board_run.json](board_run.json); the two earlier runs are kept as they were. Each build is
named here by its build stamp, a hash of the design's source and constraint files.

| Attempt | Build stamp | Outcome | What was fixed before the next attempt |
|---|---|---|---|
| 1 | `a3c1f853` | 15 of 17 runs gave the expected verdict. The 2nd and 3rd repeats of `bram_random_rw` failed the model comparison: the board's read data differed from what the transaction model predicted. The 3 repeats of `periph_regs` passed, but gave 3 different digests, so the runs were not repeatable. The run lines are in [board_run_build2_attempt.log](board_run_build2_attempt.log). | The model assumed block RAM starts each run at zero. Block RAM keeps its contents between runs, so the model now treats words not written in the run as unknown. The demo peripheral had a free-running counter and stall pattern; they now advance only while a program runs, so a run repeats exactly. |
| 2 | `c3ed8fb8` | 17 of 17 runs gave the expected verdict, inside the recommended operating conditions: [board_run_build3.json](board_run_build3.json). | The checker did not yet check that every VALID stays low while reset is held, and its reset-exit rule overlapped the write-response and read-response rules. A rule for VALID during reset was added, the reset-exit rule was narrowed so no two rules overlap, and the core's width check moved to elaboration time. |
| 3 | `19a86593` | 17 of 17: the result, [board_run.json](board_run.json). | |
