/-
  Specification file for brief 139d: one CORDIC iteration of arith/sincos/rtl/sincos_cordic.sv and arith/atan2_mag/rtl/atan2_cordic.sv (circular) and of
  arith/exp2/rtl/exp2_cordic.sv and arith/log2/rtl/log2_cordic.sv (hyperbolic), for every shift and every value.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (the verif/lean_approvals.yaml of sincos, atan2_mag, exp2 and
  log2 have no entry: every statement shows "statement not approved").

  What is modelled. An iteration at shift i moves (x, y) to (x - d y 2^-i, y + d x 2^-i) (circular) or (x + d y 2^-i, y + d x 2^-i) (hyperbolic) with the direction d = +1 or -1,
  so d * d = 1. Multiplying both coordinates by u = 2^i keeps everything in the integers: the new pair is (u x -+ d y, u y + d x). `circ_step_norm` says the circular step multiplies
  the squared length by exactly u^2 + 1, whatever the direction, i.e. 1 + 4^-i in the unscaled iteration: the gain of the CORDIC is a fixed product of constants that does not depend on the
  data (which is why the magnitude constant 1 / gain of atan2_mag and the start value of sincos_cordic are constants). `hyp_step_invariant` says the hyperbolic step multiplies x^2 - y^2 by
  exactly u^2 - 1: the quantity that stays the same up to the constant hyperbolic gain, which exp2_cordic's start value (1 / gain, 0) relies on (it ends at cosh z and sinh z) and log2_cordic's
  start (m + 1, m - 1) preserves. NOT modelled: the floor in the arithmetic shift of the RTL (the step is exact here), the angle accumulator and the convergence (that the directions chosen drive z or
  y to zero: the exhaustive simulations and the error-bound proofs cover it at the listed widths), the rounding and the register stages. The Lean text is a hand transcription of the
  adder pair of one iteration, tested only through those.
-/
namespace ArithCordic

theorem circ_step_norm (x y d u : Int) (hd : d * d = 1) :
    (u * x - d * y) * (u * x - d * y) + (u * y + d * x) * (u * y + d * x) = (u * u + 1) * (x * x + y * y) := by
  grind

theorem hyp_step_invariant (x y d u : Int) (hd : d * d = 1) :
    (u * x + d * y) * (u * x + d * y) - (u * y + d * x) * (u * y + d * x) = (u * u - 1) * (x * x - y * y) := by
  grind

end ArithCordic
