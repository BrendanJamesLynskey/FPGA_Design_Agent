/-
  Specification file for brief 139d: the quadrant split of the phase in arith/sincos/rtl/sincos_lerp.sv, sincos_poly2.sv and sincos_cordic.sv, for every phase width.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (arith/sincos/verif/lean_approvals.yaml has no entry: every
  statement shows "statement not approved").

  What is modelled. The phase is a natural number below 4 * 2^k (PH = k + 2 bits); the RTL's `assign {q, idx, d} = phase` (and `{q, o} = phase`) takes its top two bits as the
  quadrant q and the remaining k bits as the angle o inside it, which is `q = phase / 2^k` and `o = phase % 2^k`. `quadrant_split` says that q is below 4 and that q * 2^k + o
  is the phase again (nothing is lost); `quadrant_join` says that any quadrant below 4 and any angle below 2^k, put together, split back into the same two numbers (so the
  split is a bijection between the phases and the (quadrant, angle) pairs, for every k). NOT modelled: that sine and cosine of the phase are the quadrant map of the first
  quadrant's values (that is real analysis on sin(x + pi/2) = cos x; here it is checked by the exhaustive simulation and the SymbiYosys error-bound proofs against the exact
  functions at the listed widths), the table lookup and the arithmetic. The Lean text is a hand transcription of the bit-field split, tested only through those.
-/
namespace ArithQuadrant

theorem quadrant_split (k p : Nat) (hp : p < 4 * 2 ^ k) :
    p / 2 ^ k < 4 ∧ (p / 2 ^ k) * 2 ^ k + p % 2 ^ k = p := by
  constructor
  · rw [Nat.div_lt_iff_lt_mul (Nat.two_pow_pos k)]
    omega
  · have := Nat.div_add_mod p (2 ^ k)
    rw [Nat.mul_comm] at this
    exact this

theorem quadrant_join (k q o : Nat) (ho : o < 2 ^ k) :
    (q * 2 ^ k + o) / 2 ^ k = q ∧ (q * 2 ^ k + o) % 2 ^ k = o := by
  constructor
  · rw [Nat.add_comm, Nat.add_mul_div_right _ _ (Nat.two_pow_pos k), Nat.div_eq_of_lt ho]
    omega
  · rw [Nat.add_comm, Nat.add_mul_mod_self_right]
    exact Nat.mod_eq_of_lt ho

end ArithQuadrant
