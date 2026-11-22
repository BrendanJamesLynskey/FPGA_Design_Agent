/-
  Specification file for brief 139b: the restoring digit recurrence of arith/isqrt (isqrt_restoring_iter.sv and isqrt_restoring_pipe.sv),
  for every width.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR THE OWNER'S APPROVAL (no approval is recorded; the
  testplan arith/isqrt/verif/testplan.yaml shows the item as "statement not approved"). The recurrence takes the radicand two bits at a time,
  most significant pair first: `rsqrt w x` is (root, remainder) after the top `w` pairs of `x` (the radicand has 2w bits). Nothing here models
  registers, widths, clocks or the non-restoring variant (its statement is in arith/isqrt/spec.md and is not proved). The meaning of
  "floor square root" is the pair of facts `root * root + rem = x` and `rem <= 2 * root`, which determine the root uniquely.
-/
namespace Arith.Isqrt

/-- Restoring square root: shift two radicand bits into the remainder, try to subtract 4*root + 1, keep the difference and append a 1 to the
    root if it fits, otherwise append a 0. -/
def rsqrt : Nat → Nat → Nat × Nat
  | 0, _ => (0, 0)
  | w + 1, x =>
    let p := rsqrt w (x / 4)
    let r := 4 * p.2 + x % 4
    let t := 4 * p.1 + 1
    if t ≤ r then (2 * p.1 + 1, r - t) else (2 * p.1, r)

/-- The recurrence is a floor square root for every width: `root^2 + rem = x` and `rem <= 2 * root`, hence `root^2 <= x < (root+1)^2`. -/
theorem rsqrt_correct (w x : Nat) (hx : x < 4 ^ w) :
    (rsqrt w x).1 * (rsqrt w x).1 + (rsqrt w x).2 = x ∧ (rsqrt w x).2 ≤ 2 * (rsqrt w x).1 := by
  induction w generalizing x with
  | zero =>
    have : x = 0 := by simpa using hx
    subst this; simp [rsqrt]
  | succ w ih =>
    have hm : x / 4 < 4 ^ w := by
      have : 4 ^ (w + 1) = 4 * 4 ^ w := by rw [Nat.pow_succ]; omega
      omega
    obtain ⟨i1, i2⟩ := ih (x / 4) hm
    simp only [rsqrt]
    generalize rsqrt w (x / 4) = p at i1 i2
    obtain ⟨R, rem⟩ := p
    simp only at i1 i2 ⊢
    have h : R * (2 * R) = 2 * (R * R) := by rw [Nat.mul_left_comm]
    have e2 : (2 * R) * (2 * R) = 4 * (R * R) := by
      rw [Nat.mul_assoc, h]; omega
    have e1 : (2 * R + 1) * (2 * R + 1) = 4 * (R * R) + 4 * R + 1 := by
      simp only [Nat.mul_add, Nat.add_mul, Nat.mul_one, Nat.one_mul, e2]
      omega
    split
    · rename_i hc
      refine ⟨?_, by omega⟩
      rw [e1]; omega
    · rename_i hc
      refine ⟨?_, by omega⟩
      rw [e2]; omega

end Arith.Isqrt
