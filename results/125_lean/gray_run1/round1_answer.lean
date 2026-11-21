/-
  Specification file for brief 125: the gray code of a counter, for every width.

  The definitions and the theorem statements in this file are the SPECIFICATION. They were written
  by the brief-125 executor and are LEFT FOR THE OWNER'S APPROVAL (see designs/b96_kr260_10g/verif/lean_approvals.yaml:
  no approval is recorded). The proof writer may fill in each proof and add helper theorems, nothing else
  (tools/statements.py checks this, and flow/trace_v1.py's frozen-statement gate checks an approved statement).

  What is modelled. The write pointer and the read pointer of designs/b96_kr260_10g/rtl/rate_match_gp.sv are binary
  counters of CW = AW + 1 bits that count modulo 2^CW. Each crosses to the other clock through an xpm_cdc_gray
  macro (rate_match_gp.sv lines 77-82), which registers `bin ^ (bin >> 1)` in the source clock, passes that gray value
  through DEST_SYNC_FF flops, and decodes it in the destination clock. The encoder and decoder are inside AMD's macro,
  so they are not our RTL. The transcription below is of the macro's behaviour as written down in the repository's own
  behavioural model flow/cdc_models/xpm_cdc_models.sv (lines 71-85, written from UG974), and cross-checked against that
  model in simulation by Gray/CrossCheck.lean. Nothing here models the synchroniser flops, the clocks or metastability:
  the theorems say that if a sampled gray value is the old or the new gray value of a counter step, the decoded value is
  the old or the new count (`gray_sample`). Why a one-bit change makes that so is the content of `gray_step`.
-/
namespace Gray

/-- The encoder of xpm_cdc_gray: `bin ^ (bin >> 1)` (xpm_cdc_models.sv line 78: `src_in_bin ^ (src_in_bin >> 1)`). -/
def bin2gray {n : Nat} (b : BitVec n) : BitVec n := b ^^^ (b >>> 1)

/-- The reduction XOR of all `n` bits of `x`. -/
def parity {n : Nat} (x : BitVec n) : Bool :=
  (List.range n).foldl (fun a k => xor a (x.getLsbD k)) false

/-- The decoder of xpm_cdc_gray: output bit `j` is the reduction XOR of the gray bits `j` to `n-1`
    (xpm_cdc_models.sv line 84: `b[i] = ^dg[WIDTH-1:i]`), that is the parity of `g >> j`. -/
def gray2bin {n : Nat} (g : BitVec n) : BitVec n :=
  (List.range n).foldl
    (fun acc j => acc ||| ((BitVec.ofBool (parity (g >>> j))).zeroExtend n <<< j)) 0#n

theorem xor_false' (a : Bool) : xor a false = a := by cases a <;> rfl

theorem xor_assoc' (a b c : Bool) : xor (xor a b) c = xor a (xor b c) := by
  cases a <;> cases b <;> cases c <;> rfl

theorem lsb_ge {n : Nat} (x : BitVec n) (i : Nat) (h : n ≤ i) : x.getLsbD i = false := by
  first
  | exact BitVec.getLsbD_of_ge x i h
  | exact BitVec.getLsbD_ge x i h
  | (simp [BitVec.getLsbD]
     exact Nat.testBit_lt_two_pow
       (Nat.lt_of_lt_of_le x.isLt (Nat.pow_le_pow_right (by decide) h)))

theorem shr_bit {n : Nat} (g : BitVec n) (i k : Nat) :
    (g >>> i).getLsbD k = g.getLsbD (i + k) := by
  first
  | exact BitVec.getLsbD_ushiftRight g i k
  | (simp [BitVec.getLsbD_ushiftRight]; done)
  | (simp [BitVec.getLsbD_ushiftRight, Nat.add_comm]; done)
  | (show (g.toNat >>> i).testBit k = g.toNat.testBit (i + k)
     simp [Nat.testBit_shiftRight])

theorem bv_ext {n : Nat} (x y : BitVec n) (h : ∀ j, j < n → x.getLsbD j = y.getLsbD j) :
    x = y := by
  first
  | exact BitVec.eq_of_getLsbD_eq (fun i => h i.val i.isLt)
  | (apply BitVec.eq_of_getElem_eq
     intro i hi
     simpa [BitVec.getLsbD_eq_getElem hi] using h i hi)
  | (ext i hi
     simpa using h i hi)

theorem gbit {n : Nat} (b : BitVec n) (j : Nat) :
    (bin2gray b).getLsbD j = xor (b.getLsbD j) (b.getLsbD (j+1)) := by
  first
  | (unfold bin2gray
     rw [BitVec.getLsbD_xor, shr_bit, Nat.add_comm 1 j])
  | (simp [bin2gray, BitVec.getLsbD_ushiftRight, Nat.add_comm]; done)

theorem S_succ (f : Nat → Bool) (m : Nat) :
    (List.range (m+1)).foldl (fun a k => xor a (f k)) false
      = xor ((List.range m).foldl (fun a k => xor a (f k)) false) (f m) := by
  first
  | (rw [List.range_succ, List.foldl_append]; done)
  | (rw [List.range_succ, List.foldl_append]; rfl)
  | simp [List.range_succ]

theorem S_false (f : Nat → Bool) (h : ∀ k, f k = false) (m : Nat) :
    (List.range m).foldl (fun a k => xor a (f k)) false = false := by
  induction m with
  | zero => rfl
  | succ m ih =>
    rw [S_succ, ih, h]
    all_goals rfl

theorem S_shift (f g : Nat → Bool) (hg : ∀ k, g k = f (k+1)) (m : Nat) :
    (List.range (m+1)).foldl (fun a k => xor a (f k)) false
      = xor (f 0) ((List.range m).foldl (fun a k => xor a (g k)) false) := by
  induction m with
  | zero =>
    rw [S_succ f 0]
    first | simp | (cases f 0 <;> rfl)
  | succ m ih =>
    rw [S_succ f (m+1), ih, S_succ g m, ← hg m, xor_assoc']

theorem parity_eq {n : Nat} (x : BitVec n) (f : Nat → Bool) (h : ∀ k, x.getLsbD k = f k) :
    parity x = (List.range n).foldl (fun a k => xor a (f k)) false := by
  simp only [parity, h]

theorem parity_high {n : Nat} (g : BitVec n) (j : Nat) (hj : n ≤ j) :
    parity (g >>> j) = false := by
  have e : parity (g >>> j)
      = (List.range n).foldl (fun a k => xor a (g.getLsbD (j + k))) false :=
    parity_eq _ (fun k => g.getLsbD (j + k)) (fun k => shr_bit g j k)
  rw [e]
  exact S_false (fun k => g.getLsbD (j + k)) (fun k => lsb_ge g _ (by omega)) n

theorem parity_rec {n : Nat} (g : BitVec n) (j : Nat) (hj : j < n) :
    parity (g >>> j) = xor (g.getLsbD j) (parity (g >>> (j+1))) := by
  obtain ⟨m, rfl⟩ : ∃ m, n = m + 1 := ⟨n - 1, by omega⟩
  have hA : ∀ k, (g >>> j).getLsbD k = g.getLsbD (j + k) := fun k => shr_bit g j k
  have hB : ∀ k, (g >>> (j+1)).getLsbD k = g.getLsbD (j + (k+1)) := fun k => by
    rw [shr_bit]
    exact congrArg g.getLsbD (by omega)
  have e1 : parity (g >>> j)
      = (List.range (m+1)).foldl (fun a k => xor a (g.getLsbD (j + k))) false :=
    parity_eq (g >>> j) (fun k => g.getLsbD (j + k)) hA
  have e1' : (List.range (m+1)).foldl (fun a k => xor a (g.getLsbD (j + k))) false
      = xor (g.getLsbD j)
          ((List.range m).foldl (fun a k => xor a (g.getLsbD (j + (k+1)))) false) :=
    S_shift (fun k => g.getLsbD (j + k)) (fun k => g.getLsbD (j + (k+1))) (fun k => rfl) m
  have eB : parity (g >>> (j+1))
      = (List.range (m+1)).foldl (fun a k => xor a (g.getLsbD (j + (k+1)))) false :=
    parity_eq (g >>> (j+1)) (fun k => g.getLsbD (j + (k+1))) hB
  have e2 : (List.range (m+1)).foldl (fun a k => xor a (g.getLsbD (j + (k+1)))) false
      = xor ((List.range m).foldl (fun a k => xor a (g.getLsbD (j + (k+1)))) false)
          (g.getLsbD (j + (m+1))) :=
    S_succ (fun k => g.getLsbD (j + (k+1))) m
  have e3 : g.getLsbD (j + (m+1)) = false := lsb_ge g _ (by omega)
  rw [e1, e1', eB, e2, e3, xor_false']

theorem term_bit {n : Nat} (p : Bool) (k j : Nat) (hj : j < n) :
    ((((BitVec.ofBool p).zeroExtend n) <<< k).getLsbD j) = (decide (j = k) && p) := by
  have hn : 0 < n := by omega
  by_cases h : j = k
  · have hk : k < n := by omega
    first
    | (simp [h, hk, hn]; done)
    | (simp [BitVec.getLsbD_shiftLeft, h, hk, hn]; done)
    | (cases p <;> simp [BitVec.getLsbD_shiftLeft, BitVec.getLsbD_setWidth,
        BitVec.zeroExtend_eq_setWidth, BitVec.getLsbD_ofBool, h, hk, hn]; done)
    | (cases p <;> simp [BitVec.getLsbD_shiftLeft, BitVec.getLsbD_zeroExtend,
        BitVec.getLsbD_ofBool, h, hk, hn]; done)
  · rcases Nat.lt_or_ge j k with hlt | hge
    · have hnk : ¬ k ≤ j := by omega
      first
      | (simp [h, hlt, hj, hn]; done)
      | (simp [BitVec.getLsbD_shiftLeft, h, hlt, hj, hn]; done)
      | (simp [BitVec.getLsbD_shiftLeft, h, hlt, hj, hn, hnk]; done)
    · have e : ¬ j - k = 0 := by omega
      have e2 : ¬ j ≤ k := by omega
      have e3 : ¬ j < k := by omega
      first
      | (simp [h, e, e2, e3, hj, hn]; done)
      | (simp [BitVec.getLsbD_shiftLeft, h, e, e2, e3, hj, hn]; done)
      | (cases p <;> simp [BitVec.getLsbD_shiftLeft, BitVec.getLsbD_setWidth,
          BitVec.zeroExtend_eq_setWidth, BitVec.getLsbD_ofBool, h, e, e2, e3, hj, hn]; done)
      | (cases p <;> simp [BitVec.getLsbD_shiftLeft, BitVec.getLsbD_zeroExtend,
          BitVec.getLsbD_ofBool, h, e, e2, e3, hj, hn]; done)

theorem fold_bit {n : Nat} (g : BitVec n) (j : Nat) (hj : j < n) (l : List Nat) :
    ∀ acc : BitVec n,
    ((l.foldl (fun acc k => acc ||| ((BitVec.ofBool (parity (g >>> k))).zeroExtend n <<< k)) acc).getLsbD j)
      = (acc.getLsbD j || (decide (j ∈ l) && parity (g >>> j))) := by
  induction l with
  | nil => intro acc; simp
  | cons k l ih =>
    intro acc
    rw [List.foldl_cons, ih, BitVec.getLsbD_or, term_bit _ k j hj]
    by_cases h : j = k
    · rw [← h]
      cases acc.getLsbD j <;> cases parity (g >>> j) <;> by_cases hm : j ∈ l <;> simp [hm]
    · simp [h]

theorem g2b_bit {n : Nat} (g : BitVec n) (j : Nat) (hj : j < n) :
    (gray2bin g).getLsbD j = parity (g >>> j) := by
  have h : (gray2bin g).getLsbD j
      = ((0#n).getLsbD j || (decide (j ∈ List.range n) && parity (g >>> j))) :=
    fold_bit g j hj (List.range n) 0#n
  rw [h]
  have hm : j ∈ List.range n := List.mem_range.mpr hj
  simp [hm]

theorem parity_gray {n : Nat} (b : BitVec n) :
    ∀ d j, n - j = d → parity (bin2gray b >>> j) = b.getLsbD j := by
  intro d
  induction d with
  | zero =>
    intro j hj
    rw [parity_high _ j (by omega)]
    exact (lsb_ge b j (by omega)).symm
  | succ d ih =>
    intro j hj
    rw [parity_rec (bin2gray b) j (by omega), ih (j+1) (by omega), gbit]
    cases b.getLsbD j <;> cases b.getLsbD (j+1) <;> rfl

theorem one_bit {n : Nat} (hn : 0 < n) (i : Nat) :
    (1 : BitVec n).getLsbD i = decide (i = 0) := by
  first
  | (simp [hn]; done)
  | (have h1 : (1 : BitVec n).toNat = 1 := by
       have h2 : 2 ^ 1 ≤ 2 ^ n := Nat.pow_le_pow_right (by decide) hn
       show 1 % 2 ^ n = 1
       exact Nat.mod_eq_of_lt (by omega)
     show (1 : BitVec n).toNat.testBit i = _
     rw [h1]
     cases i <;> simp [Nat.testBit_succ])

theorem succ_bits {n : Nat} (hn : 0 < n) (b : BitVec n) :
    ∃ f : Nat → Bool, f 0 = true ∧ (∀ j, f (j+1) = (b.getLsbD j && f j)) ∧
      ∀ j, j < n → (b + 1).getLsbD j = xor (b.getLsbD j) (f j) := by
  refine ⟨fun j => xor ((1 : BitVec n).getLsbD j) (BitVec.carry j b 1 false), ?_, ?_, ?_⟩
  · show xor ((1 : BitVec n).getLsbD 0) (BitVec.carry 0 b 1 false) = true
    first
    | (simp [one_bit hn, BitVec.carry_zero]; done)
    | (simp [one_bit hn, BitVec.carry]; done)
  · intro j
    show xor ((1 : BitVec n).getLsbD (j+1)) (BitVec.carry (j+1) b 1 false)
        = (b.getLsbD j && xor ((1 : BitVec n).getLsbD j) (BitVec.carry j b 1 false))
    rw [BitVec.carry_succ]
    cases j with
    | zero =>
      cases b.getLsbD 0 <;>
      first
      | (simp [one_bit hn, BitVec.carry_zero, BitVec.atLeastTwo]; done)
      | (simp [one_bit hn, BitVec.carry_zero]; done)
    | succ j =>
      cases b.getLsbD (j+1) <;> cases BitVec.carry (j+1) b 1 false <;>
      first
      | (simp [one_bit hn, BitVec.atLeastTwo]; done)
      | (simp [one_bit hn]; done)
  · intro j hj
    show (b + 1).getLsbD j
        = xor (b.getLsbD j) (xor ((1 : BitVec n).getLsbD j) (BitVec.carry j b 1 false))
    first
    | exact BitVec.getLsbD_add hj b 1
    | exact BitVec.getLsbD_add hj
    | rw [BitVec.getLsbD_add hj]

theorem diff_iff {n : Nat} (b : BitVec n) (f : Nat → Bool)
    (hf1 : ∀ j, f (j+1) = (b.getLsbD j && f j))
    (hb : ∀ j, j < n → (b + 1).getLsbD j = xor (b.getLsbD j) (f j))
    (j : Nat) (hj : j < n) :
    ((bin2gray b).getLsbD j ≠ (bin2gray (b + 1)).getLsbD j) ↔
      (f j = true ∧ (b.getLsbD j = false ∨ j + 1 = n)) := by
  rw [gbit b j, gbit (b+1) j, hb j hj]
  by_cases h : j + 1 < n
  · rw [hb (j+1) h, hf1 j]
    have hne : ¬ (j + 1 = n) := by omega
    cases b.getLsbD j <;> cases b.getLsbD (j+1) <;> cases f j <;> simp [hne]
  · have hn1 : j + 1 = n := by omega
    rw [lsb_ge (b+1) (j+1) (by omega), lsb_ge b (j+1) (by omega)]
    cases b.getLsbD j <;> cases f j <;> simp [hn1]

theorem f_mono {n : Nat} (b : BitVec n) (f : Nat → Bool)
    (hf1 : ∀ j, f (j+1) = (b.getLsbD j && f j)) :
    ∀ d j, f (j + d) = true → f j = true := by
  intro d
  induction d with
  | zero => intro j h; exact h
  | succ d ih =>
    intro j h
    have h' : f (j + d + 1) = true := by rw [Nat.add_assoc]; exact h
    have h2 : (b.getLsbD (j+d) && f (j+d)) = true := by rw [← hf1]; exact h'
    have h3 : f (j+d) = true := by
      revert h2
      cases b.getLsbD (j+d) <;> cases f (j+d) <;> simp
    exact ih j h3

theorem find_first {n : Nat} (b : BitVec n) (f : Nat → Bool)
    (hf1 : ∀ j, f (j+1) = (b.getLsbD j && f j)) :
    ∀ k m, m + k + 1 = n → f m = true →
      ∃ i, m ≤ i ∧ i < n ∧ (f i = true ∧ (b.getLsbD i = false ∨ i + 1 = n)) ∧
        ∀ j, m ≤ j → j < i → (f (j+1) = true ∧ b.getLsbD j = true) := by
  intro k
  induction k with
  | zero =>
    intro m hm hfm
    exact ⟨m, Nat.le_refl _, by omega, ⟨hfm, Or.inr (by omega)⟩, fun j h1 h2 => by omega⟩
  | succ k ih =>
    intro m hm hfm
    cases hbm : b.getLsbD m with
    | false =>
      exact ⟨m, Nat.le_refl _, by omega, ⟨hfm, Or.inl hbm⟩, fun j h1 h2 => by omega⟩
    | true =>
      have hf' : f (m+1) = true := by simp [hf1 m, hbm, hfm]
      obtain ⟨i, hi1, hi2, hi3, hi4⟩ := ih (m+1) (by omega) hf'
      refine ⟨i, by omega, hi2, hi3, ?_⟩
      intro j hj1 hj2
      by_cases hjm : j = m
      · rw [hjm]
        exact ⟨hf', hbm⟩
      · exact hi4 j (by omega) hj2

/-- req: B96-F-LEAN-GRAY-STEP
    For every width `n > 0` and every counter value `b`, the gray codes of `b` and of `b + 1` (the counter
    steps by one and wraps from 2^n - 1 to 0) differ in exactly one bit. -/
theorem gray_step {n : Nat} (hn : 0 < n) (b : BitVec n) :
    ∃ i : Fin n, ∀ j : Fin n,
      ((bin2gray b).getLsbD j.val ≠ (bin2gray (b + 1)).getLsbD j.val) ↔ j = i := by
  obtain ⟨f, hf0, hf1, hb⟩ := succ_bits hn b
  obtain ⟨i, _, hi_lt, hD, hch⟩ := find_first b f hf1 (n-1) 0 (by omega) hf0
  refine ⟨⟨i, hi_lt⟩, fun j => ?_⟩
  refine (diff_iff b f hf1 hb j.val j.isLt).trans ?_
  constructor
  · intro hj
    obtain ⟨h1, h2⟩ := hj
    apply Fin.ext
    show j.val = i
    rcases Nat.lt_trichotomy j.val i with hlt | heq | hgt
    · exfalso
      obtain ⟨_, hb'⟩ := hch j.val (Nat.zero_le _) hlt
      rcases h2 with h2 | h2
      · exact absurd (hb'.symm.trans h2) (by decide)
      · omega
    · exact heq
    · exfalso
      have hj1 : f (i+1) = true := by
        have := f_mono b f hf1 (j.val - (i+1)) (i+1)
          (by rw [show i + 1 + (j.val - (i+1)) = j.val by omega]; exact h1)
        exact this
      rcases hD.2 with h3 | h3
      · rw [hf1 i, h3] at hj1
        simp at hj1
      · have := j.isLt
        omega
  · intro h
    have hv : j.val = i := congrArg Fin.val h
    rw [hv]
    exact hD

/-- req: B96-F-LEAN-GRAY-DECODE
    For every width and every binary value, the decoder inverts the encoder. -/
theorem gray2bin_bin2gray {n : Nat} (b : BitVec n) : gray2bin (bin2gray b) = b := by
  apply bv_ext
  intro j hj
  rw [g2b_bit (bin2gray b) j hj]
  exact parity_gray b (n - j) j rfl

/-- req: B96-F-LEAN-GRAY-DECODE
    For every width and every gray value, the encoder inverts the decoder (so the two are a bijection). -/
theorem bin2gray_gray2bin {n : Nat} (g : BitVec n) : bin2gray (gray2bin g) = g := by
  apply bv_ext
  intro j hj
  rw [gbit, g2b_bit g j hj]
  have hr := parity_rec g j hj
  by_cases h : j + 1 < n
  · rw [g2b_bit g (j+1) h, hr]
    cases g.getLsbD j <;> cases parity (g >>> (j+1)) <;> rfl
  · rw [lsb_ge (gray2bin g) (j+1) (by omega), hr, parity_high g (j+1) (by omega)]
    cases g.getLsbD j <;> rfl

/-- req: B96-F-LEAN-GRAY-DECODE
    A sampled gray value that is the code of the old count or of the new count decodes to the old or the new count,
    for every width and every count (the property the pointer crossing relies on). -/
theorem gray_sample {n : Nat} (hn : 0 < n) (b g : BitVec n)
    (h : g = bin2gray b ∨ g = bin2gray (b + 1)) : gray2bin g = b ∨ gray2bin g = b + 1 := by
  rcases h with h | h
  · left
    rw [h]
    exact gray2bin_bin2gray b
  · right
    rw [h]
    exact gray2bin_bin2gray (b + 1)

end Gray
