/-
  Specification file for brief 139c: the radix-4 digit recurrence of arith/sqrt_r4 (sqrt_r4_iter.sv and sqrt_r4_pipe.sv), for every width.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR A HUMAN'S APPROVAL (no approval is recorded; the
  testplan arith/sqrt_r4/verif/testplan.yaml shows the item as "statement not approved"). `r4sqrt w x` is (root, remainder) after the top `w`
  nibbles of `x` (the radicand has 4w bits), one radix-4 digit per nibble: the largest digit d in {0,1,2,3} whose trial value d * (8q + d)
  does not exceed the shifted remainder 16 * rem + nibble. Nothing here models registers, widths or clocks. "Floor square root" is the pair of
  facts `root * root + rem = x` and `rem <= 2 * root`, which determine the root uniquely.
-/
namespace Arith.SqrtR4

/-- One step: from the root `q` and remainder `r` so far and the next nibble, choose the digit and subtract its trial value. -/
def step (q r nib : Nat) : Nat × Nat :=
  let s := 16 * r + nib
  if 24 * q + 9 ≤ s then (4 * q + 3, s - (24 * q + 9))
  else if 16 * q + 4 ≤ s then (4 * q + 2, s - (16 * q + 4))
  else if 8 * q + 1 ≤ s then (4 * q + 1, s - (8 * q + 1))
  else (4 * q, s)

/-- Radix-4 square root: shift four radicand bits into the remainder and take the next digit; the top nibbles come first. -/
def r4sqrt : Nat → Nat → Nat × Nat
  | 0, _ => (0, 0)
  | w + 1, x =>
    let p := r4sqrt w (x / 16)
    step p.1 p.2 (x % 16)

-- req: SQRT4-F-LEAN-RECURRENCE
/-- The recurrence is a floor square root for every width: `root^2 + rem = x` and `rem <= 2 * root`, hence `root^2 <= x < (root+1)^2`. -/
theorem r4sqrt_correct (w x : Nat) (hx : x < 16 ^ w) :
    (r4sqrt w x).1 * (r4sqrt w x).1 + (r4sqrt w x).2 = x ∧ (r4sqrt w x).2 ≤ 2 * (r4sqrt w x).1 := by
  induction w generalizing x with
  | zero =>
    have : x = 0 := by simpa using hx
    subst this; simp [r4sqrt]
  | succ w ih =>
    have hm : x / 16 < 16 ^ w := by
      have : 16 ^ (w + 1) = 16 * 16 ^ w := by rw [Nat.pow_succ]; omega
      omega
    obtain ⟨i1, i2⟩ := ih (x / 16) hm
    simp only [r4sqrt]
    generalize r4sqrt w (x / 16) = p at i1 i2
    obtain ⟨q, r⟩ := p
    simp only at i1 i2 ⊢
    have e0 : (4 * q) * (4 * q) = 16 * (q * q) := by
      rw [Nat.mul_assoc, Nat.mul_left_comm q 4 q, ← Nat.mul_assoc]
    have e3 : (4 * q + 3) * (4 * q + 3) = 16 * (q * q) + 24 * q + 9 := by
      simp only [Nat.mul_add, Nat.add_mul, e0] <;> omega
    have e2 : (4 * q + 2) * (4 * q + 2) = 16 * (q * q) + 16 * q + 4 := by
      simp only [Nat.mul_add, Nat.add_mul, e0] <;> omega
    have e1 : (4 * q + 1) * (4 * q + 1) = 16 * (q * q) + 8 * q + 1 := by
      simp only [Nat.mul_add, Nat.add_mul, e0] <;> omega
    simp only [step]
    split
    · rename_i hc
      refine ⟨?_, by omega⟩
      rw [e3]; omega
    · split
      · rename_i hc1 hc2
        refine ⟨?_, by omega⟩
        rw [e2]; omega
      · split
        · rename_i hc1 hc2 hc3
          refine ⟨?_, by omega⟩
          rw [e1]; omega
        · rename_i hc1 hc2 hc3
          refine ⟨?_, by omega⟩
          rw [e0]; omega

end Arith.SqrtR4
