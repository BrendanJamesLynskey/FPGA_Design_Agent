/-
  Specification file for brief 139a: the integer adder/subtractor family, for every width.

  The definitions and the theorem statements in this file are the SPECIFICATION. They were written by the brief-139a executor and are LEFT FOR
  THE OWNER'S APPROVAL (arith/adder/verif/lean_approvals.yaml has no entry: every statement shows "statement not approved").

  What is modelled. The numbers are natural numbers; an n-bit adder returns the sum modulo 2^n (`sumN`) and the carry out (`carryN`).
  `csSum` and `csCarry` are the structure of arith/adder/rtl/adder_carry_select.sv with two blocks: a low block of m bits, and a high block of k bits
  computed twice (carry in 0 and carry in 1) and selected by the carry out of the low block. `cs_correct` says that structure adds, for all m, k
  and all operands. `sub_is_add_complement` says that the subtract path of all three variants, a + ~b + ~bin on n bits (~x = 2^n - 1 - x, the
  inverted operand and the inverted carry in), gives a - b - bin modulo 2^n and a carry out equal to 1 exactly when there is no borrow.
  Nothing here models the registers of the pipelined variant, the signed-overflow flag, clocks or timing; the Lean text is a hand transcription of the
  RTL's structure (arith/adder/rtl/adder_carry_select.sv, the g_first and g_sel blocks), tested against the RTL only through the simulation and the
  SymbiYosys proofs of the same structure, not generated from it. A carry-select adder of more than two blocks is the same argument applied to the
  high block again; only the two-block case is stated.
-/
namespace ArithAdder

/-- The sum bits of an n-bit adder: (a + b + c) mod 2^n. -/
def sumN (n a b c : Nat) : Nat := (a + b + c) % 2 ^ n

/-- The carry out of an n-bit adder: (a + b + c) div 2^n. -/
def carryN (n a b c : Nat) : Nat := (a + b + c) / 2 ^ n

/-- Carry-select sum: a low block of m bits, then a high block of k bits taken from the copy with carry in 1 or the copy with carry in 0, chosen by the low block's carry out. -/
def csSum (m k al ah bl bh c : Nat) : Nat :=
  sumN m al bl c + 2 ^ m * (if carryN m al bl c = 1 then sumN k ah bh 1 else sumN k ah bh 0)

/-- Carry-select carry out: the high block's carry out, chosen the same way. -/
def csCarry (m k al ah bl bh c : Nat) : Nat :=
  if carryN m al bl c = 1 then carryN k ah bh 1 else carryN k ah bh 0

theorem carry_le_one (n a b c : Nat) (ha : a < 2 ^ n) (hb : b < 2 ^ n) (hc : c ≤ 1) : carryN n a b c ≤ 1 := by
  have hp : 0 < 2 ^ n := Nat.two_pow_pos n
  have h : (a + b + c) / 2 ^ n < 2 := by
    rw [Nat.div_lt_iff_lt_mul hp]
    omega
  unfold carryN
  omega

theorem cs_correct (m k a b c : Nat) (hc : c ≤ 1) :
    csSum m k (a % 2 ^ m) (a / 2 ^ m) (b % 2 ^ m) (b / 2 ^ m) c = (a + b + c) % 2 ^ (m + k) ∧
    csCarry m k (a % 2 ^ m) (a / 2 ^ m) (b % 2 ^ m) (b / 2 ^ m) c = (a + b + c) / 2 ^ (m + k) := by
  have hP : 0 < 2 ^ m := Nat.two_pow_pos m
  have hQ : 0 < 2 ^ k := Nat.two_pow_pos k
  have hal : a % 2 ^ m < 2 ^ m := Nat.mod_lt _ hP
  have hbl : b % 2 ^ m < 2 ^ m := Nat.mod_lt _ hP
  have hcl := carry_le_one m (a % 2 ^ m) (b % 2 ^ m) c hal hbl hc
  have hT : a + b + c = (a % 2 ^ m + b % 2 ^ m + c) + 2 ^ m * (a / 2 ^ m + b / 2 ^ m) := by
    have e1 := Nat.mod_add_div a (2 ^ m)
    have e2 := Nat.mod_add_div b (2 ^ m)
    rw [Nat.mul_add]
    omega
  have h1 : (a + b + c) % 2 ^ m = (a % 2 ^ m + b % 2 ^ m + c) % 2 ^ m := by
    rw [hT, Nat.add_mul_mod_self_left]
  have h2 : (a + b + c) / 2 ^ m = carryN m (a % 2 ^ m) (b % 2 ^ m) c + (a / 2 ^ m + b / 2 ^ m) := by
    rw [hT, Nat.add_mul_div_left _ _ hP]
    rfl
  have h3 : (a + b + c) % 2 ^ (m + k) = (a + b + c) % 2 ^ m + 2 ^ m * ((a + b + c) / 2 ^ m % 2 ^ k) := by
    rw [Nat.pow_add, Nat.mod_mul]
  have h4 : (a + b + c) / 2 ^ (m + k) = (a + b + c) / 2 ^ m / 2 ^ k := by
    rw [Nat.pow_add, Nat.div_div_eq_div_mul]
  have key : ∀ d : Nat, d ≤ 1 → (if d = 1 then sumN k (a / 2 ^ m) (b / 2 ^ m) 1 else sumN k (a / 2 ^ m) (b / 2 ^ m) 0)
      = (d + (a / 2 ^ m + b / 2 ^ m)) % 2 ^ k := by
    intro d hd
    unfold sumN
    rcases Nat.le_one_iff_eq_zero_or_eq_one.mp hd with h | h <;> subst h <;> simp [Nat.add_comm]
  have key2 : ∀ d : Nat, d ≤ 1 → (if d = 1 then carryN k (a / 2 ^ m) (b / 2 ^ m) 1 else carryN k (a / 2 ^ m) (b / 2 ^ m) 0)
      = (d + (a / 2 ^ m + b / 2 ^ m)) / 2 ^ k := by
    intro d hd
    unfold carryN
    rcases Nat.le_one_iff_eq_zero_or_eq_one.mp hd with h | h <;> subst h <;> simp [Nat.add_comm]
  constructor
  · unfold csSum
    rw [key _ hcl, h3, h1, h2]
    unfold sumN
    rfl
  · unfold csCarry
    rw [key2 _ hcl, h4, h2]

/-- Subtraction as the three variants do it: a - b - bin is a + ~b + ~bin on n bits, with ~x = 2^n - 1 - x. The sum is a - b - bin modulo 2^n, and the carry out is 1 exactly when there is no borrow (b + bin <= a). -/
theorem sub_is_add_complement (n a b bin : Nat) (ha : a < 2 ^ n) (hb : b < 2 ^ n) (hbin : bin ≤ 1) :
    sumN n a (2 ^ n - 1 - b) (1 - bin) = (a + 2 ^ n - (b + bin)) % 2 ^ n ∧
    carryN n a (2 ^ n - 1 - b) (1 - bin) = (if b + bin ≤ a then 1 else 0) := by
  have hX : 0 < 2 ^ n := Nat.two_pow_pos n
  unfold sumN carryN
  have hV : a + (2 ^ n - 1 - b) + (1 - bin) = a + 2 ^ n - (b + bin) := by omega
  rw [hV]
  by_cases h : b + bin ≤ a
  · have hE : a + 2 ^ n - (b + bin) = (a - (b + bin)) + 2 ^ n := by omega
    have hlt : a - (b + bin) < 2 ^ n := by omega
    rw [hE, Nat.add_mod_right, Nat.add_div_right _ hX, Nat.div_eq_of_lt hlt]
    simp [h]
  · have hlt : a + 2 ^ n - (b + bin) < 2 ^ n := by omega
    rw [Nat.div_eq_of_lt hlt]
    simp [h]

end ArithAdder
