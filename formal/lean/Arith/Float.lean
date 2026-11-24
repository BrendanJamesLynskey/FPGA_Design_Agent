/-
  Specification file for brief 139e: three small integer facts under the rounding and normalisation of the floating-point library (arith/fp_common/fp_pack.sv, fp_norm.sv), for
  every width.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (arith/fp_add/verif/lean_approvals.yaml, fp_mul and fp_fma have no
  entry: every statement shows "statement not approved").

  Why only these. Core Lean has no IEEE-754 library (Flocq is a Coq library; Mathlib's floats are a different development). What a float function MEANS (the rounding and special-case
  rules) is written in arith/fp_common/fp_ref.py and arith/fp_*/spec.md, and its agreement with the RTL is shown by simulation and by SymbiYosys at tiny formats, not here. Proving
  that the fp_ref rounding is IEEE round-to-nearest-even for every format is research (it needs a real-number or rational model of the format and its rounding); it is NOT attempted.
  What is proved here are the integer lemmas the RTL's tricks rest on:

  * `pack_inc_carry`: fp_pack adds the rounding increment to the packed {exponent, fraction} pattern. For a pattern e * m + f with fraction f < m (m = 2^MAN) the increment either
    bumps the fraction, or, when the fraction is all ones, carries into the exponent and leaves a zero fraction; so a rounding overflow of the significand needs no special case.
  * `norm_shift`: fp_norm shifts left by lz = (NW - 1) - msb. For a value whose leading one is at bit k < NW, the result has its leading one at bit NW - 1.
  * `rne_nearest_even`: the rounding decision of fp_pack (increment when the guard bit is set and either a lower bit is set or the least significant kept bit is one) gives the
    integer nearest to the exact quotient, and where two are equally near, the even one. The kept part is `hi`, the discarded part `lo` below a threshold `2 * h` (h = half a unit).

  What is NOT modelled: widths of vectors, the exponent range, subnormal handling, flush to zero, infinities and NaNs, and the sticky bit's construction (an OR of the shifted-out bits).
  The Lean text is a hand transcription of the idea of those RTL lines, tested only through the simulations and proofs listed in the testplans.
-/
namespace ArithFloat

/-- The packed pattern with the rounding increment added: either the fraction goes up by one, or (fraction all ones) the exponent goes up by one and the fraction is zero. -/
theorem pack_inc_carry (e f m : Nat) (_hf : f + 1 ≤ m) :
    e * m + f + 1 = if f + 1 = m then (e + 1) * m else e * m + (f + 1) := by
  split
  · rename_i h
    rw [Nat.add_mul, Nat.one_mul]
    omega
  · omega

/-- Left-normalising a value with its leading one at bit k (2^k <= v < 2^(k+1)) by NW - 1 - k places puts the leading one at bit NW - 1. -/
theorem norm_shift (v k n : Nat) (hlo : 2 ^ k ≤ v) (hhi : v < 2 ^ (k + 1)) (hk : k < n) :
    2 ^ (n - 1) ≤ v * 2 ^ (n - 1 - k) ∧ v * 2 ^ (n - 1 - k) < 2 ^ n := by
  obtain ⟨j, hj⟩ : ∃ j, n = k + 1 + j := ⟨n - (k + 1), by omega⟩
  have h1 : n - 1 = k + j := by omega
  have h2 : n - 1 - k = j := by omega
  rw [h2, h1, hj]
  constructor
  · rw [Nat.pow_add]
    exact Nat.mul_le_mul_right _ hlo
  · rw [Nat.pow_add (2 : Nat) (k + 1) j]
    exact Nat.mul_lt_mul_of_pos_right hhi (Nat.two_pow_pos j)

/-- The rounding increment. `hi` is the kept part, `lo` the discarded part below the threshold `2 * h`; increment when the discarded part is above half, or exactly half and `hi` is odd. -/
def rneInc (hi lo h : Nat) : Nat := if h < lo ∨ (lo = h ∧ hi % 2 = 1) then 1 else 0

/-- The rounded value is nearest to the exact value hi * (2h) + lo (within half a unit h) and, if it is exactly h away from it, even. -/
theorem rne_nearest_even (hi lo h : Nat) (hlo : lo < 2 * h) :
    ((hi + rneInc hi lo h) * (2 * h) ≤ hi * (2 * h) + lo + h) ∧
    (hi * (2 * h) + lo ≤ (hi + rneInc hi lo h) * (2 * h) + h) ∧
    (((hi + rneInc hi lo h) * (2 * h) = hi * (2 * h) + lo + h ∨ hi * (2 * h) + lo = (hi + rneInc hi lo h) * (2 * h) + h) →
      (hi + rneInc hi lo h) % 2 = 0) := by
  unfold rneInc
  by_cases hc : h < lo ∨ (lo = h ∧ hi % 2 = 1)
  · simp only [hc, ↓reduceIte]
    rw [Nat.add_mul, Nat.one_mul]
    rcases hc with hc | ⟨hc1, hc2⟩
    · refine ⟨by omega, by omega, ?_⟩
      intro hh
      omega
    · subst hc1
      refine ⟨by omega, by omega, ?_⟩
      intro _
      omega
  · simp only [hc, ↓reduceIte, Nat.add_zero]
    have hnot : lo ≤ h ∧ (lo = h → hi % 2 = 0) := by omega
    refine ⟨by omega, by omega, ?_⟩
    intro hh
    omega

end ArithFloat
