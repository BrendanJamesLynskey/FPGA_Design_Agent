# latency_race: a planted testbench race, for the second-method latency rule (brief 189 item 7)

`rtl/lat_pipe.sv` is a three-clock pipeline (true latency 3). `lat_tb.sv` measures it two ways: a cycle counter (one process increments,
another stamps) and the simulator's own clock. `+RACY=0` and `+RACY=1` plant the defect (blocking increment read on the same edge by
another process: the stamp reads whatever the simulator's process order gives; Icarus 12.0 prints 2 and 4). `+RACY=2` is the repair
(non-blocking increment: always 3). The simulator-clock method reads 3 in every variant.

Planted defect for a review benchmark: the design plus a bench that prints a plausible wrong number. **Not added to the brief-84 benchmark
in this brief:** that benchmark lives in the private repo and its held-out split is not read by executors; the planner can add this design
as a development task there. Truth: the bench's counter method is racy; the correct latency is 3 clocks.
Ideas from Edwards 2026, ch 15; all code written here.
