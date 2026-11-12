# Earlier board attempts

The board plan ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml)) was written before the first board run and has
not changed. It was run three times; only the last run, on the final build, is the result
([board_run.json](board_run.json)). The earlier runs are kept as they were.

| Attempt | Build (stamp) | Outcome | What changed after it |
|---|---|---|---|
| 1 | build 2 (`a3c1f853`) | 15 of 17 runs passed; the 2nd and 3rd repeats of `bram_random_rw` failed the model comparison, and the 3 repeats of `periph_regs` gave 3 different digests. The final operating-conditions read was refused (another Vivado job was running), so no JSON was written: [board_run_build2_attempt.log](board_run_build2_attempt.log) has the run lines. | The transaction model treated block RAM as zero at the start of a run; it now treats words not written in the run as unknown (block RAM keeps its contents). The demo peripheral's free-running counter and stall pattern made runs unrepeatable; they now run only while a program runs (RTL change, build 3). |
| 2 | build 3 (`c3ed8fb8`, build ID `05236f86`) | 17 of 17 runs passed, inside the recommended operating conditions: [board_run_build3.json](board_run_build3.json). | A review found the checker did not check that VALID stays low while reset is held, and that its reset-exit rule overlapped the write- and read-response rules. Rule 9 (IN_RESET) was added, rule 7 narrowed, and the core's width check moved to elaboration time (RTL change, build 4). |
| 3 | build 4 | the result: [board_run.json](board_run.json) | |
