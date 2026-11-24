/-
  Specification file for brief 139a: the radix-4 Booth recoding of arith/multiplier/rtl/mult_booth_r4.sv, for every multiplier width.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (arith/multiplier/verif/lean_approvals.yaml
  has no entry: every statement shows "statement not approved").

  What is modelled. The multiplier b, extended to an even number of bits 2n (sign-extended when signed; zero-extended with at least one extra zero
  bit when unsigned), is read as n groups of two bits, least significant group first: the pair (x0, x1) of group i is (b[2i], b[2i+1]). The RTL's
  digit of group i is d_i = -2 b[2i+1] + b[2i] + b[2i-1] (b[-1] = 0), the case table of mult_booth_r4.sv's always_comb block, and the product is the
  sum of d_i * a * 4^i. `boothSum p L` is the sum of d_i * 4^i over the groups of L, where `p` is the bit below the first group (0 in the RTL).
  `booth_correct` says that sum equals the two's-complement value of the 2n-bit pattern, `gval L - 4^n * msb`; `booth_unsigned` says that for a
  pattern whose top bit is 0 (the unsigned case, which the RTL guarantees by its extra zero bit) it equals the unsigned value. So for every width the
  digits reproduce the multiplier, and each partial product d_i * a is added with the weight 4^i the RTL gives it. What is NOT modelled: the
  selection of +a, +2a, -a, -2a and 0 from the three bits (the case table) and the arithmetic of the adders; those are covered by the exhaustive
  simulation and the SymbiYosys equivalence with a plain `*` at the widths listed in arith/multiplier/verif. The Lean text is a hand transcription of
  the recoding, tested only through those.
-/
namespace ArithBooth

/-- A bit as an integer. -/
def bi (x : Bool) : Int := if x then 1 else 0

/-- The unsigned value of a list of 2-bit groups, least significant group first: group (x0, x1) has weight 4^i and value x0 + 2 x1. -/
def gval : List (Bool × Bool) → Int
  | [] => 0
  | (x0, x1) :: r => bi x0 + 2 * bi x1 + 4 * gval r

/-- The most significant bit of the pattern: the second bit of the last group (0 for an empty list). -/
def top : List (Bool × Bool) → Bool
  | [] => false
  | [(_, x1)] => x1
  | _ :: g :: r => top (g :: r)

/-- The sum of the radix-4 Booth digits d_i * 4^i, with d_i = -2 b[2i+1] + b[2i] + b[2i-1]; `p` is the bit below the first group. -/
def boothSum : Bool → List (Bool × Bool) → Int
  | _, [] => 0
  | p, (x0, x1) :: r => (-2 * bi x1 + bi x0 + bi p) + 4 * boothSum x1 r

theorem booth_correct (L : List (Bool × Bool)) (p : Bool) (hL : L ≠ []) :
    boothSum p L = bi p + gval L - 4 ^ L.length * bi (top L) := by
  induction L generalizing p with
  | nil => exact absurd rfl hL
  | cons g r ih =>
    obtain ⟨x0, x1⟩ := g
    cases r with
    | nil =>
      cases x0 <;> cases x1 <;> cases p <;> simp [boothSum, gval, top, bi]
    | cons g2 r2 =>
      have h := ih x1 (by simp)
      have ht : top ((x0, x1) :: g2 :: r2) = top (g2 :: r2) := rfl
      have hl : ((x0, x1) :: g2 :: r2).length = (g2 :: r2).length + 1 := rfl
      have e1 : boothSum p ((x0, x1) :: g2 :: r2) = (-2 * bi x1 + bi x0 + bi p) + 4 * boothSum x1 (g2 :: r2) := rfl
      have e2 : gval ((x0, x1) :: g2 :: r2) = bi x0 + 2 * bi x1 + 4 * gval (g2 :: r2) := rfl
      have e3 : (4 : Int) ^ ((g2 :: r2).length + 1) * bi (top (g2 :: r2)) = 4 * (4 ^ (g2 :: r2).length * bi (top (g2 :: r2))) := by
        rw [Int.pow_succ, Int.mul_comm ((4 : Int) ^ (g2 :: r2).length) 4, Int.mul_assoc]
      rw [e1, e2, ht, hl, e3, h]
      generalize (4 : Int) ^ (g2 :: r2).length * bi (top (g2 :: r2)) = u
      cases x0 <;> cases x1 <;> cases p <;> simp [bi] <;> omega

theorem booth_unsigned (L : List (Bool × Bool)) (h : top L = false) : boothSum false L = gval L := by
  cases L with
  | nil => rfl
  | cons g r =>
    have := booth_correct (g :: r) false (by simp)
    rw [this, h]
    simp [bi]

end ArithBooth
