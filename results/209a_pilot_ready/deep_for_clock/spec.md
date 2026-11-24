# A 32-bit multiply-accumulate with no pipeline registers (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. The clock is the 25 MHz clock on C3, but I want it to run at 250 MHz from an MMCM.*

One block, `clk` at 250 MHz (4 ns), with a synchronous reset. Inputs `a`, `b` (signed 32 bits) and `c` (signed 64 bits), all registered at the input.
Every clock the registered inputs give `y = a * b + c` (signed 64 bits), and `y` goes straight to a register at the output.
There must be **no register between the input registers and the output register**: I want the product and the addition in a single clock, in plain
logic, on the fabric, with no DSP slice (the attribute `(* use_dsp = "no" *)` on the multiplier). Two LEDs: `led[0]` is the xor of all bits of `y`,
`led[1]` is the xor of all bits of `a`. The inputs come from a 64-bit linear-feedback shift register inside the design, running every clock (the polynomial and seed are yours),
so the design needs no inputs. No registers or host access: I only want to see it build.
