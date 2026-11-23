/-
  Specification file for brief 139c: the radix-4 SRT digit recurrence of arith/divider_hr (divider_hr_iter.sv, divider_hr_cpa.sv, divider_hr_pipe.sv),
  for every number of digit steps K.

  The definitions and the theorem statements here are the SPECIFICATION and are LEFT FOR A HUMAN'S APPROVAL (no approval is recorded; the testplan
  arith/divider_hr/verif/testplan.yaml shows the items as "statement not approved"). The digit-selection rule is abstract: `sel u` is the digit chosen
  for the partial remainder `u`, and the hypothesis `hsel` is the CONTAINMENT property the selection table must have (a step from a bounded remainder
  ends in a bounded remainder). The table's containment is NOT proved here: it is established by an exhaustive search with exact fractions
  (arith/divider_hr/model.py, derive_thresholds) and, at each fixed width, by the step lemmas checked with SymbiYosys (formal/divider_hr_lemma_fv.sv).
  What Lean proves is the part that holds for every K and every selection rule with that property: after K steps b * Q + U = 4**K * (b * q1 + u1) with
  U bounded, and the correction (take Q - 1 and add b when U is negative) gives exactly the quotient and the remainder of integer division. Nothing here
  models registers, widths, the carry-save form or the on-the-fly conversion (the conversion lemma L4 is checked by SymbiYosys for the widths it covers).
-/
namespace Arith.DividerHr

/-- The convergence bound: |u| <= 2b/3, written without absolute values. -/
def Bounded (b u : Int) : Prop := -(2 * b) ≤ 3 * u ∧ 3 * u ≤ 2 * b

/-- `n` digit steps from quotient `q` and remainder `u`: u' = 4u - d*b and q' = 4q + d with d = sel u. -/
def run (b : Int) (sel : Int → Int) : Nat → Int → Int → Int × Int
  | 0, q, u => (q, u)
  | n + 1, q, u => run b sel n (4 * q + sel u) (4 * u - sel u * b)

-- req: DIVHR-F-LEAN-RECURRENCE
/-- Every digit step keeps `b * Q + U` four times larger and the remainder bounded: after `n` steps from a bounded remainder,
    `b * Q + U = 4**n * (b * q + u)` and `U` is bounded, for every `n`. -/
theorem run_spec (b : Int) (sel : Int → Int) (hsel : ∀ u, Bounded b u → Bounded b (4 * u - sel u * b)) :
    ∀ (n : Nat) (q u : Int), Bounded b u →
      b * (run b sel n q u).1 + (run b sel n q u).2 = 4 ^ n * (b * q + u) ∧ Bounded b (run b sel n q u).2 := by
  intro n
  induction n with
  | zero => intro q u hu; simp [run, hu]
  | succ n ih =>
    intro q u hu
    have h := ih (4 * q + sel u) (4 * u - sel u * b) (hsel u hu)
    simp only [run]
    refine ⟨?_, h.2⟩
    rw [h.1]
    have inner : b * (4 * q + sel u) + (4 * u - sel u * b) = 4 * (b * q + u) := by
      have e : b * (4 * q + sel u) = 4 * (b * q) + b * sel u := by
        rw [Int.mul_add, Int.mul_left_comm]
      have c : sel u * b = b * sel u := Int.mul_comm _ _
      omega
    rw [inner, Int.pow_succ, Int.mul_assoc]

-- req: DIVHR-F-LEAN-RECURRENCE
/-- The correction: from `b * Q + U = N` with `U` bounded, the quotient is `Q - 1` and the remainder `U + b` when `U < 0`, otherwise `Q` and `U`; the pair is exactly the
    quotient and remainder of integer division of `N` by `b`, and the remainder is in `[0, b)`. -/
theorem fix_correct (b N Q U : Int) (hb : 0 < b) (h : b * Q + U = N) (hU : Bounded b U) :
    (if U < 0 then U + b else U) < b ∧ 0 ≤ (if U < 0 then U + b else U) ∧
    (if U < 0 then Q - 1 else Q) = N / b ∧ (if U < 0 then U + b else U) = N % b := by
  obtain ⟨h1, h2⟩ := hU
  split
  · rename_i hn
    have hr : 0 ≤ U + b := by omega
    have hr2 : U + b < b := by omega
    have e : b * (Q - 1) = b * Q - b := by rw [Int.mul_sub, Int.mul_one]
    have key := (Int.ediv_emod_unique hb (a := N) (b := b) (q := Q - 1) (r := U + b)).2 ⟨by omega, hr, hr2⟩
    exact ⟨hr2, hr, key.1.symm, key.2.symm⟩
  · rename_i hn
    have hr2 : U < b := by omega
    have key := (Int.ediv_emod_unique hb (a := N) (b := b) (q := Q) (r := U)).2 ⟨by omega, by omega, hr2⟩
    exact ⟨hr2, by omega, key.1.symm, key.2.symm⟩

-- req: DIVHR-F-LEAN-RECURRENCE
/-- The whole division: with a first step that leaves a bounded remainder (`a = b * q1 + u1`), K further steps and the correction give
    `floor(4**K * a / b)` and `4**K * a mod b`, for every K. -/
theorem divide_correct (b a q1 u1 : Int) (K : Nat) (sel : Int → Int) (hb : 0 < b) (hfirst : a = b * q1 + u1) (hu1 : Bounded b u1)
    (hsel : ∀ u, Bounded b u → Bounded b (4 * u - sel u * b)) :
    let s := run b sel K q1 u1
    (if s.2 < 0 then s.2 + b else s.2) < b ∧ 0 ≤ (if s.2 < 0 then s.2 + b else s.2) ∧
    (if s.2 < 0 then s.1 - 1 else s.1) = (4 ^ K * a) / b ∧ (if s.2 < 0 then s.2 + b else s.2) = (4 ^ K * a) % b := by
  intro s
  have hs := run_spec b sel hsel K q1 u1 hu1
  have hN : b * s.1 + s.2 = 4 ^ K * a := by rw [hs.1, hfirst]
  exact fix_correct b (4 ^ K * a) s.1 s.2 hb hN hs.2

end Arith.DividerHr
