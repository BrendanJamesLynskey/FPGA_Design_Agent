# A chain of 24 dependent multiplies in one clock (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. The clock is the 25 MHz clock on C3 (40 ns), used directly, no PLL.*

One block with a synchronous reset. A 32-bit linear-feedback shift register inside the design (polynomial and seed are yours) steps every clock and gives
the value `a`. Then, all in **one clock cycle between two registers**:

`x0 = a`, and for i from 1 to 24: `x_i = x_(i-1) * x_(i-1) + k_i`, all unsigned 32-bit, wrapping at 2^32, with `k_i` a different constant of your choice for each step.
`y = x24` goes into a 32-bit register, and `led[0]` is the exclusive-or of all bits of `y`; `led[1]` is the exclusive-or of all bits of `a`.

There must be **no register inside the chain**: I want the 24 dependent multiplications as one combinational path, not pipelined, not folded over several clocks.
(This is a test of how the build tools behave, not a useful design.) No registers or host access; I only want to see it build.
