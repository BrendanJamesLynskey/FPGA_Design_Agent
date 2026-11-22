/-
  Specification file for brief 139c: the exact-arithmetic Newton-Raphson and Goldschmidt steps behind arith/recip, arith/rsqrt and arith/div_nr.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR A HUMAN'S APPROVAL (no approval is recorded; the testplans
  arith/recip, arith/rsqrt and arith/div_nr (verif/testplan.yaml) show the items as "statement not approved"). They are about the EXACT map, over the integers with a
  common scale `S` (the integer that stands for 1.0): the reciprocal step y -> y * (2 - b * y), the reciprocal-square-root step y -> y * (3 - x * y**2) / 2 and the
  Goldschmidt update (n, d) -> (n * r, d * r) with r = 2 - d. Each is stated as a polynomial identity that holds for every integer value (so every width and
  every table), and the one-sidedness follows from it. The RTL truncates (floors) at every shift and carries two guard bits: those truncation errors, and the error
  bound that results, are NOT in Lean; they are measured over every input at small widths and proved for all input sequences by SymbiYosys at fixed widths.
  The seed table's accuracy (the starting error e0) is likewise measured, not proved here.
-/
namespace Arith.Newton

-- req: RECIP-F-LEAN-NEWTON, DIVNR-F-LEAN-GS
/-- Reciprocal step. With `S` the scale of 1.0, `b` the divisor and `y` the estimate, the new estimate is `y * (2 * S - b * y)` over `S`: the new residual
    `S * S - b * y1` equals the square of the old residual `S - b * y`. The relative error is squared. -/
theorem recip_step_residual (S b y : Int) :
    S * S - b * (y * (2 * S - b * y)) = (S - b * y) * (S - b * y) := by
  have e : b * (y * (2 * S - b * y)) = (b * y) * (2 * S - b * y) := by rw [← Int.mul_assoc]
  rw [e]
  generalize b * y = p
  have h1 : p * (2 * S - p) = 2 * (S * p) - p * p := by
    have c : p * S = S * p := Int.mul_comm _ _
    have d : p * (2 * S) = 2 * (p * S) := Int.mul_left_comm _ _ _
    rw [Int.mul_sub]
    omega
  have h2 : (S - p) * (S - p) = S * S - 2 * (S * p) + p * p := by
    simp only [Int.mul_sub, Int.sub_mul, Int.mul_comm p S]
    omega
  omega

-- req: RECIP-F-LEAN-NEWTON, DIVNR-F-LEAN-GS
/-- The exact Newton reciprocal never overshoots: `b * y1 <= S * S`, i.e. the new estimate is at most the exact reciprocal (for every integer `b` and `y`). -/
theorem recip_step_one_sided (S b y : Int) :
    b * (y * (2 * S - b * y)) ≤ S * S := by
  have h := recip_step_residual S b y
  have hsq : 0 ≤ (S - b * y) * (S - b * y) := by
    rcases Int.le_total 0 (S - b * y) with h0 | h0
    · exact Int.mul_nonneg h0 h0
    · exact Int.mul_nonneg_of_nonpos_of_nonpos h0 h0
  omega

-- req: DIVNR-F-LEAN-GS
/-- Goldschmidt: multiplying numerator and denominator by the same factor keeps their ratio: `n * b = d * a` implies `(n * r) * b = (d * r) * a`, so after any
    number of iterations `n_k * b = d_k * a`: the quotient is `n_k` when `d_k` is 1. -/
theorem gs_ratio_invariant (a b n d r : Int) (h : n * b = d * a) : (n * r) * b = (d * r) * a := by
  rw [Int.mul_right_comm, h, Int.mul_right_comm]

-- req: DIVNR-F-LEAN-GS
/-- Goldschmidt's denominator step is the reciprocal step with divisor 1: `S * S - d * r' = (S - d)**2` for the new `d' = d * (2 * S - d)`; the denominator
    approaches 1.0 from below once `d <= S`, and its distance from 1.0 is squared at each iteration. -/
theorem gs_denominator_residual (S d : Int) : S * S - d * (2 * S - d) = (S - d) * (S - d) := by
  have h := recip_step_residual S 1 d
  simpa [Int.one_mul] using h


-- req: RSQRT-F-LEAN-NEWTON
/-- Reciprocal-square-root step. With `S` the scale of 1.0 and `T` standing for `x * y * y` (so `T = S` when `y` is exactly `1 / sqrt(x)`), the new estimate is
    `y * (3 * S - T)` over `2 * S`, and `x * y1 * y1` is `T * (3 * S - T)**2 / (4 * S * S)`. The identity: `4 * S**3 - T * (3 * S - T)**2 = (S - T)**2 * (4 * S - T)`. -/
theorem rsqrt_step_residual (S T : Int) :
    4 * S * S * S - T * ((3 * S - T) * (3 * S - T)) = ((S - T) * (S - T)) * (4 * S - T) := by
  grind

-- req: RSQRT-F-LEAN-NEWTON
/-- One-sidedness: when `T <= 4 * S` (that is, `x * y * y <= 4`, true for every estimate in the range the table produces) the new estimate does not exceed
    the exact value: `T * (3 * S - T)**2 <= 4 * S**3` (so `x * y1 * y1 <= 1`). -/
theorem rsqrt_step_one_sided (S T : Int) (h : T ≤ 4 * S) :
    T * ((3 * S - T) * (3 * S - T)) ≤ 4 * S * S * S := by
  have id := rsqrt_step_residual S T
  have hsq : 0 ≤ (S - T) * (S - T) := by
    rcases Int.le_total 0 (S - T) with h0 | h0
    · exact Int.mul_nonneg h0 h0
    · exact Int.mul_nonneg_of_nonpos_of_nonpos h0 h0
  have hp : 0 ≤ ((S - T) * (S - T)) * (4 * S - T) := Int.mul_nonneg hsq (by omega)
  omega

end Arith.Newton
