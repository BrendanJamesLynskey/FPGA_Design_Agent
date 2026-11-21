/-
  Specification file for brief 139b: the recursive-halving leading-zero count of arith/lzc_norm (lzc_tree.sv), for every width 2^k.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR THE OWNER'S APPROVAL (no approval is recorded; the
  testplan arith/lzc_norm/verif/testplan.yaml shows the item as "statement not approved"). `lzcTree k x` is lzc_tree.sv for a word of 2^k bits:
  a word of one bit is its own leaf; otherwise the count of the upper half if that half is not zero, else half the width plus the count of the
  lower half. The theorem says what the count means without reference to the algorithm: a non-zero word `x` of `P = 2^k` bits with count `c`
  satisfies `2^(P-1-c) <= x < 2^(P-c)`. The stagewise variants and the zero-padding of a width that is not a power of two are not modelled
  (arith/lzc_norm/spec.md says so); they are covered by the simulation and the bounded formal checks.
-/
namespace Arith.Lzc

/-- (count, non-zero) of a word of 2^k bits by recursive halving (halves of 2^(k-1) bits; the upper half is `x / 2^(2^(k-1))`). -/
def lzcTree : Nat → Nat → Nat × Bool
  | 0, x => (0, x != 0)
  | k + 1, x =>
    let hi := lzcTree k (x / 2 ^ (2 ^ k))
    let lo := lzcTree k (x % 2 ^ (2 ^ k))
    if hi.2 then (hi.1, true) else (2 ^ k + lo.1, lo.2)

/-- For every k and every word of 2^k bits: the flag says "not zero", and a non-zero word's count `c` is below the width and brackets the word:
    `2^(P-1-c) <= x < 2^(P-c)` with `P = 2^k`. -/
theorem lzcTree_correct (k x : Nat) (hx : x < 2 ^ (2 ^ k)) :
    ((lzcTree k x).2 = true ↔ x ≠ 0) ∧
    (x ≠ 0 → (lzcTree k x).1 < 2 ^ k ∧ 2 ^ (2 ^ k - 1 - (lzcTree k x).1) ≤ x ∧ x < 2 ^ (2 ^ k - (lzcTree k x).1)) := by
  induction k generalizing x with
  | zero =>
    have h1 : x < 2 := by simpa using hx
    simp only [lzcTree]
    refine ⟨by simp, fun hne => ?_⟩
    have : x = 1 := by omega
    subst this; simp
  | succ k ih =>
    have hHpos : 0 < 2 ^ k := Nat.two_pow_pos k
    have hP : 2 ^ (2 ^ (k + 1)) = 2 ^ (2 ^ k) * 2 ^ (2 ^ k) := by
      rw [Nat.pow_succ, Nat.pow_mul, Nat.pow_two]
    obtain ⟨ihh1, ihh2⟩ := ih (x / 2 ^ (2 ^ k)) (by
      have hApos : 0 < 2 ^ (2 ^ k) := Nat.two_pow_pos _
      rw [Nat.div_lt_iff_lt_mul hApos]; rw [hP] at hx; exact hx)
    obtain ⟨ihl1, ihl2⟩ := ih (x % 2 ^ (2 ^ k)) (Nat.mod_lt _ (Nat.two_pow_pos _))
    simp only [lzcTree]
    generalize hA : 2 ^ (2 ^ k) = A at *
    generalize hH : 2 ^ k = H at *
    have hApos : 0 < A := by rw [← hA]; exact Nat.two_pow_pos _
    have hxe := Nat.div_add_mod x A
    generalize hhi : x / A = hi at *
    generalize hlo : x % A = lo at *
    have hlo_lt : lo < A := by rw [← hlo]; exact Nat.mod_lt _ hApos
    generalize lzcTree k hi = ph at *
    generalize lzcTree k lo = pl at *
    obtain ⟨ch, nh⟩ := ph
    obtain ⟨cl, nl⟩ := pl
    simp only at *
    have hk1 : 2 ^ (k + 1) = 2 * H := by rw [Nat.pow_succ]; omega
    rw [hk1]
    by_cases hn : nh = true
    · simp only [hn, if_true]
      have hhi0 : hi ≠ 0 := ihh1.mp hn
      obtain ⟨c1, c2, c3⟩ := ihh2 hhi0
      have hxpos : x ≠ 0 := by
        have : A * 1 ≤ A * hi := Nat.mul_le_mul_left A (by omega)
        omega
      refine ⟨by simp [hxpos], fun _ => ⟨by omega, ?_, ?_⟩⟩
      · have e : 2 * H - 1 - ch = H + (H - 1 - ch) := by omega
        rw [e, Nat.pow_add, hA]
        calc A * 2 ^ (H - 1 - ch) ≤ A * hi := Nat.mul_le_mul_left A c2
          _ ≤ x := by omega
      · have e : 2 * H - ch = H + (H - ch) := by omega
        rw [e, Nat.pow_add, hA]
        have h2 : 2 ^ (H - ch) = 2 * 2 ^ (H - 1 - ch) := by
          have : H - ch = (H - 1 - ch) + 1 := by omega
          rw [this, Nat.pow_succ]; omega
        calc x = A * hi + lo := hxe.symm
          _ < A * hi + A := by omega
          _ = A * (hi + 1) := by rw [Nat.mul_add, Nat.mul_one]
          _ ≤ A * 2 ^ (H - ch) := Nat.mul_le_mul_left A (by omega)
    · have hnf : nh = false := by simpa using hn
      simp only [hnf, Bool.false_eq_true, ↓reduceIte]
      have hhi0 : hi = 0 := by
        rcases Nat.eq_zero_or_pos hi with h | h
        · exact h
        · have := ihh1.mpr (by omega)
          rw [hnf] at this
          simp at this
      subst hhi0
      have hxl : x = lo := by omega
      subst hxl
      refine ⟨by simpa using ihl1, fun hne => ?_⟩
      obtain ⟨c1, c2, c3⟩ := ihl2 hne
      refine ⟨by omega, ?_, ?_⟩
      · have e : 2 * H - 1 - (H + cl) = H - 1 - cl := by omega
        rw [e]; exact c2
      · have e : 2 * H - (H + cl) = H - cl := by omega
        rw [e]; exact c3

end Arith.Lzc
