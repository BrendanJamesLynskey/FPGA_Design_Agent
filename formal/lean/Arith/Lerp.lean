/-
  Specification file for brief 139d: the linear interpolation of the segment-table variants (arith/exp2/rtl/exp2_lerp.sv, arith/log2/rtl/log2_lerp.sv and the sine lane of
  arith/sincos/rtl/sincos_lerp.sv), for every position width.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (the verif/lean_approvals.yaml of exp2, log2 and sincos have no
  entry: every statement shows "statement not approved").

  What is modelled. In a segment with break-point value c0 and slope s (the difference of the table values at the two ends of the segment, a natural number for a rising function:
  exp2, log2, the sine of the first quadrant), at position d in [0, 2^D) the RTL forms acc = c0 * 2^D + s * d and then drops the D low bits (and rounds, a monotone step that
  is not modelled here): `interp c0 s d D = (c0 * 2^D + s * d) / 2^D`. `lerp_between` says the result is never below the segment's start value c0 and never above its end value
  c0 + s, for every D, c0, s and every position d < 2^D; `lerp_mono` says it does not fall as d grows. So between break points the table variant cannot overshoot or go
  backwards. NOT modelled: the size of the error against the exact function (that is the model's measured bound, an exhaustive computation per point, and interval
  arithmetic over the function's second derivative would be a research item), the rounding, the table contents, the cosine's falling segments (a negative slope), and the clamp.
  The Lean text is a hand transcription of the RTL's `acc = c0 * 2^DB + s1 * d` lines, tested only through simulation and the SymbiYosys error-bound proofs of the RTL.
-/
namespace ArithLerp

/-- The interpolated value in coefficient units: break-point value plus slope times position, the D low bits dropped. -/
def interp (c0 s d D : Nat) : Nat := (c0 * 2 ^ D + s * d) / 2 ^ D

theorem lerp_between (c0 s d D : Nat) (hd : d < 2 ^ D) :
    c0 ≤ interp c0 s d D ∧ interp c0 s d D ≤ c0 + s := by
  unfold interp
  constructor
  · rw [Nat.le_div_iff_mul_le (Nat.two_pow_pos D)]
    exact Nat.le_add_right _ _
  · have h1 : s * d ≤ s * 2 ^ D := Nat.mul_le_mul_left s (Nat.le_of_lt hd)
    have h2 : c0 * 2 ^ D + s * d ≤ 2 ^ D * (c0 + s) := by
      rw [Nat.mul_add, Nat.mul_comm (2 ^ D) c0, Nat.mul_comm (2 ^ D) s]
      omega
    exact Nat.div_le_of_le_mul h2

theorem lerp_mono (c0 s d1 d2 D : Nat) (h : d1 ≤ d2) :
    interp c0 s d1 D ≤ interp c0 s d2 D := by
  unfold interp
  apply Nat.div_le_div_right
  have := Nat.mul_le_mul_left s h
  omega

end ArithLerp
