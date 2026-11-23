/-
  Specification file for brief 139b: fixed-point rounding (arith/fxp_round), for every width and every number of dropped bits.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR THE OWNER'S APPROVAL (no approval is recorded; the
  testplan arith/fxp_round/verif/testplan.yaml shows every item as "statement not approved"). The dropped bits are S, and `d = 2 * h` is
  2^S with `h = 2^(S-1)` the half; the theorems hold for every `h > 0`, so for every S >= 1 (the RTL's S = 0 case is the identity and
  needs no statement). Integers are exact (`Int`): nothing here models a register width, saturation or wrapping. Saturation and wrapping
  are the checks `fit` in arith/fxp_round/model.py and the simulation; the claim proved here is the one the RTL's single adder relies on:
  the carry-in form equals the textbook definition.
-/
namespace Arith.Rounding

/-- Truncate (round toward minus infinity): the arithmetic shift right by S. -/
def trunc (h : Nat) (x : Int) : Int := x / (2 * h : Nat)

/-- Round half up (ties toward plus infinity): add the half and truncate. -/
def halfUp (h : Nat) (x : Int) : Int := (x + h) / (2 * h : Nat)

/-- Convergent (round half to even), from its definition: floor plus one when the fraction is above the half, or equal to it with an odd floor. -/
def convergent (h : Nat) (x : Int) : Int :=
  let fl := x / (2 * h : Nat)
  let rem := x % (2 * h : Nat)
  if (h : Int) < rem ∨ (rem = h ∧ fl % 2 = 1) then fl + 1 else fl

/-- The form the RTL builds (arith/fxp_round/rtl/fxp_round_fold.sv): one addition of the constant `h - 1` and the bit that becomes the
    result's LSB (bit S of x, which is the floor's parity) as a carry-in, then truncate. -/
def convFold (h : Nat) (x : Int) : Int := (x + ((h : Int) - 1) + (x / (2 * h : Nat)) % 2) / (2 * h : Nat)

/-- Facts every statement uses: x = d * floor + rem, with 0 <= rem < d. -/
theorem split_fl (h : Nat) (hh : 0 < h) (x : Int) :
    ((2 * h : Nat) : Int) * (x / (2 * h : Nat)) + x % (2 * h : Nat) = x ∧
    0 ≤ x % (2 * h : Nat) ∧ x % (2 * h : Nat) < ((2 * h : Nat) : Int) := by
  refine ⟨Int.mul_ediv_add_emod x _, Int.emod_nonneg _ (by omega), Int.emod_lt_of_pos _ (by omega)⟩

/-- Truncation error: the result times 2^S is at most x and less than one unit below it. -/
theorem trunc_error (h : Nat) (hh : 0 < h) (x : Int) :
    0 ≤ x - ((2 * h : Nat) : Int) * trunc h x ∧ x - ((2 * h : Nat) : Int) * trunc h x < ((2 * h : Nat) : Int) := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  unfold trunc
  omega

/-- A quotient characterisation used for the two addition forms: if `r + d*q = a` and `0 <= r < d` then `a / d = q`. -/
theorem ediv_of (d : Nat) (hd : 0 < d) (a q r : Int) (e : r + (d : Int) * q = a) (h0 : 0 ≤ r) (h1 : r < d) : a / (d : Int) = q :=
  ((Int.ediv_emod_unique (by omega : (0 : Int) < d)).mpr ⟨e, h0, h1⟩).1

/-- Round half up equals floor plus one exactly when the fraction is at least the half. -/
theorem halfUp_def (h : Nat) (hh : 0 < h) (x : Int) :
    halfUp h x = x / (2 * h : Nat) + (if (h : Int) ≤ x % (2 * h : Nat) then 1 else 0) := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  unfold halfUp
  generalize hf : x / (2 * h : Nat) = fl at e
  generalize hr : x % (2 * h : Nat) = rem at e a b
  have e2 : ((2 * h : Nat) : Int) * (fl + 1) = ((2 * h : Nat) : Int) * fl + ((2 * h : Nat) : Int) := by rw [Int.mul_add]; omega
  split
  · exact ediv_of (2 * h) (by omega) _ _ (rem + h - ((2 * h : Nat) : Int)) (by omega) (by omega) (by omega)
  · rename_i hn
    have := ediv_of (2 * h) (by omega) (x + h) fl (rem + h) (by omega) (by omega) (by omega)
    rw [Int.add_zero]; exact this

/-- Round half up never errs by more than half a unit: -h < result*2^S - x <= h. -/
theorem halfUp_error (h : Nat) (hh : 0 < h) (x : Int) :
    -(h : Int) < ((2 * h : Nat) : Int) * halfUp h x - x ∧ ((2 * h : Nat) : Int) * halfUp h x - x ≤ h := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  rw [halfUp_def h hh x]
  generalize hf : x / (2 * h : Nat) = fl at e ⊢
  generalize hr : x % (2 * h : Nat) = rem at e a b ⊢
  have e2 : ((2 * h : Nat) : Int) * (fl + 1) = ((2 * h : Nat) : Int) * fl + ((2 * h : Nat) : Int) := by rw [Int.mul_add]; omega
  split <;> rename_i hc <;> (try simp only [Int.add_zero]) <;> omega

/-- The convergent definition and the carry-in form agree, for every x and every h > 0: this is what lets the RTL do rounding with one adder. -/
theorem convFold_eq (h : Nat) (hh : 0 < h) (x : Int) : convFold h x = convergent h x := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  unfold convFold convergent
  dsimp only
  generalize hf : x / (2 * h : Nat) = fl at e ⊢
  generalize hr : x % (2 * h : Nat) = rem at e a b ⊢
  have hc : fl % 2 = 0 ∨ fl % 2 = 1 := by omega
  have e2 : ((2 * h : Nat) : Int) * (fl + 1) = ((2 * h : Nat) : Int) * fl + ((2 * h : Nat) : Int) := by rw [Int.mul_add]; omega
  by_cases hcond : (h : Int) < rem ∨ (rem = h ∧ fl % 2 = 1)
  · rw [if_pos hcond]
    exact ediv_of (2 * h) (by omega) _ _ (rem + (h - 1) + fl % 2 - ((2 * h : Nat) : Int)) (by omega) (by omega) (by omega)
  · rw [if_neg hcond]
    exact ediv_of (2 * h) (by omega) _ _ (rem + (h - 1) + fl % 2) (by omega) (by omega) (by omega)

/-- Convergent rounding errs by at most half a unit, and a tie goes to the even result. -/
theorem convergent_error (h : Nat) (hh : 0 < h) (x : Int) :
    -(h : Int) ≤ ((2 * h : Nat) : Int) * convergent h x - x ∧ ((2 * h : Nat) : Int) * convergent h x - x ≤ h := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  unfold convergent
  dsimp only
  generalize hf : x / (2 * h : Nat) = fl at e ⊢
  generalize hr : x % (2 * h : Nat) = rem at e a b ⊢
  have e2 : ((2 * h : Nat) : Int) * (fl + 1) = ((2 * h : Nat) : Int) * fl + ((2 * h : Nat) : Int) := by rw [Int.mul_add]; omega
  split <;> rename_i hc
  · omega
  · omega

/-- A tie (fraction exactly the half) rounds to an even result. -/
theorem convergent_tie_even (h : Nat) (hh : 0 < h) (x : Int) (htie : x % (2 * h : Nat) = h) : convergent h x % 2 = 0 := by
  obtain ⟨e, a, b⟩ := split_fl h hh x
  unfold convergent
  dsimp only
  generalize hf : x / (2 * h : Nat) = fl at e ⊢
  generalize hr : x % (2 * h : Nat) = rem at e a b htie ⊢
  subst htie
  split <;> rename_i hc <;> omega

end Arith.Rounding
