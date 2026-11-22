/-
  Specification file for brief 139b: the digit recurrences of arith/divider, for every width.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR THE OWNER'S APPROVAL (no approval is recorded; the
  testplan arith/divider/verif/testplan.yaml shows every item as "statement not approved"). Nothing here models clocks, registers, pipelining
  or the RTL's register widths: the recurrences are the arithmetic of arith/divider/rtl/div_restoring_*.sv and div_nonrestoring_*.sv,
  transcribed step for step (one bit of the dividend per step, most significant first), and cross-checked against arith/divider/model.py in
  Arith/CrossCheck.lean's companion script (formal/lean/tools/crosscheck_arith.py). `restDiv d w n` is the restoring recurrence on the low `w`
  bits of `n`; `nrRun` is the non-restoring one with its signed partial remainder.
-/
namespace Arith.Divide

/-- Restoring division: the pair (quotient so far, partial remainder) after consuming the top bits of `n`.
    Step: shift the next dividend bit into the remainder, subtract the divisor if it fits (quotient bit 1) else keep it (bit 0). -/
def restDiv (d : Nat) : Nat → Nat → Nat × Nat
  | 0, _ => (0, 0)
  | w + 1, n =>
    let p := restDiv d w (n / 2)
    let r := 2 * p.2 + n % 2
    if d ≤ r then (2 * p.1 + 1, r - d) else (2 * p.1, r)

/-- The restoring recurrence computes `n / d` and `n % d` for every width. -/
theorem restDiv_correct (d w n : Nat) (hd : 0 < d) (hn : n < 2 ^ w) :
    restDiv d w n = (n / d, n % d) := by
  induction w generalizing n with
  | zero =>
    have : n = 0 := by simpa using hn
    subst this; simp [restDiv]
  | succ w ih =>
    have hm : n / 2 < 2 ^ w := by
      have : 2 ^ (w + 1) = 2 * 2 ^ w := by rw [Nat.pow_succ]; omega
      omega
    have h := ih (n / 2) hm
    simp only [restDiv, h]
    have hq := Nat.div_add_mod (n / 2) d
    have hr : (n / 2) % d < d := Nat.mod_lt _ hd
    generalize hk : d * ((n / 2) / d) = k at hq
    generalize ha : (n / 2) / d = q0
    generalize hb : (n / 2) % d = r0
    have key : ∀ q r : Nat, r < d → n = d * q + r → n / d = q ∧ n % d = r := by
      intro q r hr' he
      exact (Nat.div_mod_unique hd).mpr ⟨by omega, hr'⟩
    have e2 : d * (2 * q0 + 1) = 2 * (d * q0) + d := by rw [Nat.mul_add, Nat.mul_left_comm]; omega
    have e3 : d * (2 * q0) = 2 * (d * q0) := by rw [Nat.mul_left_comm]
    have hk' : d * q0 = k := by rw [← hk, ← ha]
    split
    · have := key (2 * q0 + 1) (2 * r0 + n % 2 - d) (by omega) (by omega)
      simp [this.1, this.2]
    · have := key (2 * q0) (2 * r0 + n % 2) (by omega) (by omega)
      simp [this.1, this.2]

/-- Division by zero: the recurrence returns all ones and the dividend (the convention in arith/divider/spec.md). -/
theorem restDiv_zero (w n : Nat) (hn : n < 2 ^ w) : restDiv 0 w n = (2 ^ w - 1, n) := by
  induction w generalizing n with
  | zero =>
    have : n = 0 := by simpa using hn
    subst this; simp [restDiv]
  | succ w ih =>
    have hm : n / 2 < 2 ^ w := by
      have : 2 ^ (w + 1) = 2 * 2 ^ w := by rw [Nat.pow_succ]; omega
      omega
    have h := ih (n / 2) hm
    have hp : 0 < 2 ^ w := Nat.two_pow_pos w
    have hp2 : 2 ^ (w + 1) = 2 * 2 ^ w := by rw [Nat.pow_succ]; omega
    simp only [restDiv, h]
    have : 0 ≤ 2 * (n / 2) + n % 2 := Nat.zero_le _
    simp
    omega

/-- Non-restoring division, signed partial remainder: the step subtracts the divisor when the remainder is not negative and adds it back
    when it is; the quotient bit is the sign of the new remainder (1 for not negative). -/
def nrStep (d : Int) (p : Int) (b : Int) : Int := if 0 ≤ p then 2 * p + b - d else 2 * p + b + d

/-- (partial remainder, quotient so far) after consuming the top bits of `n`. The quotient is kept as an `Int` only so that the proofs
    need no casts; it is never negative (see `nrRun_invariant`). -/
def nrRun (d : Nat) : Nat → Nat → Int × Int
  | 0, _ => (0, 0)
  | w + 1, n =>
    let s := nrRun d w (n / 2)
    let p := nrStep d s.1 ((n % 2 : Nat) : Int)
    (p, 2 * s.2 + if 0 ≤ p then 1 else 0)

/-- The final correction: add the divisor back to a negative remainder. -/
def nrFinal (d : Nat) (p : Int) : Int := if p < 0 then p + d else p

/-- The invariant of the non-restoring recurrence: with `n` the dividend bits consumed so far, a non-negative remainder is `n - d*Q`, a
    negative one is `n - d*(Q+1)`, the remainder lies in [-d, d), and the quotient is not negative. -/
theorem nrRun_invariant (d w n : Nat) (hd : 0 < d) (hn : n < 2 ^ w) :
    ((0 ≤ (nrRun d w n).1 → (nrRun d w n).1 = (n : Int) - (d : Int) * (nrRun d w n).2) ∧
     ((nrRun d w n).1 < 0 → (nrRun d w n).1 = (n : Int) - (d : Int) * ((nrRun d w n).2 + 1))) ∧
    (-(d : Int) ≤ (nrRun d w n).1 ∧ (nrRun d w n).1 < (d : Int)) ∧ 0 ≤ (nrRun d w n).2 := by
  induction w generalizing n with
  | zero =>
    have : n = 0 := by simpa using hn
    subst this; simp [nrRun]; omega
  | succ w ih =>
    have hm : n / 2 < 2 ^ w := by
      have : 2 ^ (w + 1) = 2 * 2 ^ w := by rw [Nat.pow_succ]; omega
      omega
    obtain ⟨⟨i1, i2⟩, i3, i4⟩ := ih (n / 2) hm
    generalize hs : nrRun d w (n / 2) = s at i1 i2 i3 i4
    obtain ⟨P, Q⟩ := s
    simp only at i1 i2 i3 i4
    have hb : (n : Int) = 2 * ((n / 2 : Nat) : Int) + ((n % 2 : Nat) : Int) := by omega
    have hb2 : ((n % 2 : Nat) : Int) ≤ 1 := by omega
    have hb3 : 0 ≤ ((n % 2 : Nat) : Int) := by omega
    simp only [nrRun, hs, nrStep]
    generalize ((n % 2 : Nat) : Int) = b at hb hb2 hb3 ⊢
    generalize hm' : ((n / 2 : Nat) : Int) = m at hb i1 i2
    have e1 : (d : Int) * (2 * Q + 1) = 2 * ((d : Int) * Q) + d := by
      rw [Int.mul_add, Int.mul_left_comm]; omega
    have e3 : (d : Int) * (2 * Q) = 2 * ((d : Int) * Q) := by rw [Int.mul_left_comm]
    have e4 : (d : Int) * (2 * Q + 1 + 1) = 2 * ((d : Int) * Q) + 2 * d := by
      rw [Int.mul_add, e1]; omega
    have e5 : (d : Int) * (2 * Q + 0 + 1) = 2 * ((d : Int) * Q) + d := by rw [Int.add_zero]; exact e1
    have e6 : (d : Int) * (Q + 1) = (d : Int) * Q + d := by rw [Int.mul_add]; omega
    by_cases hP : 0 ≤ P
    · have h1 := i1 hP
      by_cases hP' : 0 ≤ 2 * P + b - (d : Int)
      · simp only [if_pos hP, if_pos hP', Int.add_zero]
        omega
      · simp only [if_pos hP, if_neg hP', Int.add_zero]
        omega
    · have h2 := i2 (by omega)
      by_cases hP' : 0 ≤ 2 * P + b + (d : Int)
      · simp only [if_neg hP, if_pos hP', Int.add_zero]
        omega
      · simp only [if_neg hP, if_neg hP', Int.add_zero]
        omega

/-- The non-restoring recurrence with its final correction computes `n / d` and `n % d` for every width. -/
theorem nr_correct (d w n : Nat) (hd : 0 < d) (hn : n < 2 ^ w) :
    (nrRun d w n).2 = ((n / d : Nat) : Int) ∧ nrFinal d (nrRun d w n).1 = ((n % d : Nat) : Int) := by
  obtain ⟨⟨i1, i2⟩, i3, i4⟩ := nrRun_invariant d w n hd hn
  generalize nrRun d w n = s at i1 i2 i3 i4
  obtain ⟨P, Q⟩ := s
  simp only at i1 i2 i3 i4 ⊢
  have hnd := Nat.div_add_mod n d
  have hlt : n % d < d := Nat.mod_lt _ hd
  have key : ∀ (q : Int) (r : Int), 0 ≤ q → 0 ≤ r → r < d → (n : Int) = (d : Int) * q + r →
      q = ((n / d : Nat) : Int) ∧ r = ((n % d : Nat) : Int) := by
    intro q r hq0 h0 hr he
    obtain ⟨q', hq'⟩ := Int.eq_ofNat_of_zero_le hq0
    obtain ⟨r', hr'⟩ := Int.eq_ofNat_of_zero_le h0
    subst hq' hr'
    have hn' : r' + d * q' = n := by
      have : ((r' + d * q' : Nat) : Int) = (n : Int) := by push_cast; omega
      exact_mod_cast this
    have hu := (Nat.div_mod_unique hd).mpr ⟨hn', by omega⟩
    omega
  by_cases hP : 0 ≤ P
  · have h1 := i1 hP
    have := key Q P i4 hP (by omega) (by omega)
    refine ⟨this.1, ?_⟩
    simp only [nrFinal, show ¬ P < 0 by omega, ite_false]
    exact this.2
  · have h2 := i2 (by omega)
    have e : (d : Int) * (Q + 1) = (d : Int) * Q + d := by rw [Int.mul_add]; omega
    have := key Q (P + d) i4 (by omega) (by omega) (by omega)
    refine ⟨this.1, ?_⟩
    simp only [nrFinal, show P < 0 by omega, ite_true]
    exact this.2

end Arith.Divide
