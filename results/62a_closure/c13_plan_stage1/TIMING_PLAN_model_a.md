# Timing and resource plan (computed; do not edit)

TIMING AND RESOURCE PLAN (computed from the 7series delay model, 70% of the period per stage). Write the RTL to this plan: use each named template so synthesis infers the planned primitive; after synthesis a planned DSP or BRAM that comes out as LUTs or registers fails the gate.
- datapath hough_projection_and_bin_update (clock period 10.0 ns, stage budget 7.0 ns; one stage unpipelined would be 20.356 ns): 6 register stages, latency 6 clocks from the source register.
    x_times_cos (mul) -> dsp: DSP48E1 multiply fully pipelined: registered operands, then `m <= a_r * b_r;`, then `p <= m (+ c);` (AREG/BREG, MREG, PREG; a following add of another product or a constant can go in the P stage); no asynchronous reset on any of them, or synthesis builds them in fabric [5 x 8 multiply: the part has DSP48E1 slices free (1 slice)]
    y_times_sin (mul) -> dsp: DSP48E1 multiply fully pipelined: registered operands, then `m <= a_r * b_r;`, then `p <= m (+ c);` (AREG/BREG, MREG, PREG; a following add of another product or a constant can go in the P stage); no asynchronous reset on any of them, or synthesis builds them in fabric [5 x 8 multiply: the part has DSP48E1 slices free (1 slice)]
    projection_sum (add) -> carry: adder or subtractor `s <= a + b;` on the carry chain (CARRY4); a sum of three or more terms is a tree of two-input adds, registered between levels if the plan says so [adder: carry chain]
    fixed_point_rounding_shift (shift) -> wire: plain LUT logic [constant shift: wiring]
    bin_address_select (logic) -> lut: plain LUT logic [plain logic: no hard resource fits]
    bin_count_memory (memory) -> bram: block RAM: `(* ram_style = "block" *)` array, write `if (we) mem[wa] <= wd;`, synchronous read `q <= mem[ra];` (a second register `q2 <= q;` uses the RAM's output register) [1536 x 11 = 16896 bits: block RAM]
    saturating_increment (add) -> carry: adder or subtractor `s <= a + b;` on the carry chain (CARRY4); a sum of three or more terms is a tree of two-input adds, registered between levels if the plan says so [adder: carry chain]
    stage 1 (~2.416 ns, register after it: free): x_times_cos|y_times_sin: operand into AREG/BREG
    stage 2 (~2.154 ns, register after it: free): x_times_cos|y_times_sin: multiply (to MREG)
    stage 3 (~2.154 ns, register after it: free): x_times_cos|y_times_sin: M to P (post-add)
    stage 4 (~4.708 ns, register after it: fabric): x_times_cos|y_times_sin: P out to fabric; projection_sum: add level 1
    stage 5 (~5.704 ns, register after it: fabric): projection_sum: add level 2; fixed_point_rounding_shift: constant shift (wiring); bin_address_select: 2 LUT levels
    stage 6 (~5.131 ns, register after it: fabric): bin_count_memory: BRAM read (output register); saturating_increment: add level 1

Why 5 x 8 here and 9 x 9 in the delay model: the plan sizes each multiply at the operand widths the architect wrote in architecture.yaml (5 and 8 bits), while 9 x 9 is only the size the calibration build measured; the DSP stages do not depend on the width up to 25 x 18.
