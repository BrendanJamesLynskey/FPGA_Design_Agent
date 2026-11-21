/-
  Specification file for brief 124. The definitions and theorem statements in this file are
  the SPECIFICATION: they are written and approved by a human and must not be changed by the
  proof writer. Proofs live in Cksum/Proofs.lean and may only fill in the proof of each
  theorem with the same name and statement.

  Source of the RTL equations: designs/b119_tcp_fast/rtl/tcp_fast.sv, branch b119-tcp-fast,
  commit 9f8d760788e4a8afcd8756e29eca348d49858765 (fold16 at line 166, template build at
  lines 258-261, per-order sums at lines 327-336). The transcription below is MANUAL.
-/
import Std.Tactic.BVDecide

namespace Cksum

macro "split_ifs" : tactic => `(tactic| (repeat' split))

/-- Ones' complement addition of two 16-bit words (RFC 1071: add, then add the carry back). -/
def ocAdd (a b : BitVec 16) : BitVec 16 :=
  let s : BitVec 17 := a.setWidth 17 + b.setWidth 17
  s.setWidth 16 + (s.ushiftRight 16).setWidth 16

/-- The Internet checksum sum of a list of 16-bit words (before the final complement). -/
def ocSum (l : List (BitVec 16)) : BitVec 16 := l.foldl ocAdd 0

/-- The value an end-around-carry sum has: n mod 65535, with 0 kept for n = 0 and 65535 for the
    other multiples of 65535 (the representation RFC 1071 produces from a start of 0). -/
def canon (n : Nat) : Nat := if n = 0 then 0 else (n - 1) % 65535 + 1

theorem canon_id (n : Nat) (h : n ≤ 65535) : canon n = n := by
  unfold canon
  split_ifs <;> omega

theorem canon_props (n : Nat) :
    canon n % 65535 = n % 65535 ∧ (canon n = 0 → n = 0) ∧ (n = 0 → canon n = 0) := by
  unfold canon
  split_ifs <;> refine ⟨?_, ?_, ?_⟩ <;> intros <;> omega

theorem canon_canon_add (n m : Nat) : canon (canon n + m) = canon (n + m) := by
  unfold canon
  split_ifs <;> omega

theorem canon_fold1 (n : Nat) (h : n < 2^23) :
    canon (n % 2^16 + n / 2^16 % 2^16) = canon n := by
  unfold canon
  split_ifs <;> omega

theorem canon_congr (x y : Nat) (h1 : x % 65535 = y % 65535) (h2 : x = 0 → y = 0)
    (h3 : y = 0 → x = 0) : canon x = canon y := by
  unfold canon
  split_ifs <;> omega

theorem canon_recv (n : Nat) : canon (n + (65535 - canon n)) = 65535 := by
  unfold canon
  split_ifs <;> omega

theorem canon_inc1 (a m : Nat) (ha : a ≤ 65535) (hm : m ≤ 65535) :
    canon (canon (a + m) + (2^16 - 1 - m)) = (if a = 0 then 65535 else a) := by
  unfold canon
  split_ifs <;> omega

theorem canon_inc (a m m' : Nat) (ha : a ≤ 65535) (hm : m ≤ 65535) (hm' : m' ≤ 65535)
    (hne : a + m' ≠ 0) :
    canon (canon (canon (a + m) + (2^16 - 1 - m)) + m') = canon (a + m') := by
  rw [canon_inc1 a m ha hm]
  unfold canon
  split_ifs <;> omega

theorem toNat_ushr {n : Nat} (x : BitVec n) (k : Nat) :
    (x.ushiftRight k).toNat = x.toNat / 2^k := by
  have h : (x.ushiftRight k).toNat = x.toNat >>> k := by
    first | rfl | exact BitVec.toNat_ushiftRight x k | simp
  rw [h, Nat.shiftRight_eq_div_pow]

theorem ocAdd_toNat (a b : BitVec 16) : (ocAdd a b).toNat = canon (a.toNat + b.toNat) := by
  have ha := a.isLt
  have hb := b.isLt
  unfold ocAdd
  simp only [BitVec.toNat_add, BitVec.toNat_setWidth, toNat_ushr]
  unfold canon
  split_ifs <;> omega

theorem foldl_toNat (l : List (BitVec 16)) :
    ∀ acc : BitVec 16, (l.foldl ocAdd acc).toNat = canon (acc.toNat + (l.map BitVec.toNat).sum) := by
  induction l with
  | nil =>
    intro acc
    have h := acc.isLt
    simp only [List.foldl_nil, List.map_nil, List.sum_nil, Nat.add_zero]
    exact (canon_id _ (by omega)).symm
  | cons x xs ih =>
    intro acc
    simp only [List.foldl_cons, List.map_cons, List.sum_cons]
    rw [ih, ocAdd_toNat, canon_canon_add]
    exact congrArg canon (by omega)

/-- Mathematical meaning of the ones' complement sum, for lists of any length. -/
theorem ocSum_toNat (l : List (BitVec 16)) :
    (ocSum l).toNat = canon ((l.map BitVec.toNat).sum) := by
  unfold ocSum
  rw [foldl_toNat]
  have z : (0 : BitVec 16).toNat = 0 := rfl
  rw [z, Nat.zero_add]

/-! ### Transcription of the RTL of designs/b119_tcp_fast/rtl/tcp_fast.sv -/

/-- `fold16` (line 166): fold a 20-bit sum to 16 bits with two end-around carries. -/
def fold16 (x : BitVec 20) : BitVec 16 :=
  let a : BitVec 17 := (0#1 ++ x.extractLsb' 0 16) + (0#13 ++ x.extractLsb' 16 4)
  a.extractLsb' 0 16 + (0#15 ++ a.extractLsb' 16 1)

/-- `ip_tmpl` (lines 258-261): partial sum of the static IPv4 header words. -/
def ipTmpl (ttl : BitVec 8) (sip dip : BitVec 32) : BitVec 16 :=
  fold16 ((0x4500#16).setWidth 20 + (0x0063#16).setWidth 20 + (0x4000#16).setWidth 20
    + (ttl ++ 0x06#8).setWidth 20 + (sip.extractLsb' 16 16).setWidth 20 + (sip.extractLsb' 0 16).setWidth 20
    + (dip.extractLsb' 16 16).setWidth 20 + (dip.extractLsb' 0 16).setWidth 20)

/-- `ipcsum` (lines 327 and 331): template plus the IP identification, folded, complemented. -/
def rtlIpCsum (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) : BitVec 16 :=
  let ip1 : BitVec 17 := (0#1 ++ ipTmpl ttl sip dip) + (0#1 ++ id)
  ~~~ (ip1.extractLsb' 0 16 + (0#15 ++ ip1.extractLsb' 16 1))

/-- `tcp_tmpl` (line 259 and 261): partial sum of the static pseudo-header and TCP words. -/
def tcpTmpl (sip dip : BitVec 32) (sport dport : BitVec 16) : BitVec 16 :=
  fold16 ((sip.extractLsb' 16 16).setWidth 20 + (sip.extractLsb' 0 16).setWidth 20
    + (dip.extractLsb' 16 16).setWidth 20 + (dip.extractLsb' 0 16).setWidth 20
    + (0x0006#16).setWidth 20 + (0x004F#16).setWidth 20 + sport.setWidth 20 + dport.setWidth 20
    + (0x5018#16).setWidth 20)

/-- `csum` (lines 329-336): template + seq + ack + window + payload sum, folded, complemented.
    `pw` are the payload's 16-bit words; the RTL's `sump` is their 21-bit sum. -/
def rtlTcpCsum (sip dip : BitVec 32) (sport dport : BitVec 16) (seq ack : BitVec 32)
    (win : BitVec 16) (pw : List (BitVec 16)) : BitVec 16 :=
  let hdr1 : BitVec 19 := (tcpTmpl sip dip sport dport).setWidth 19
    + (seq.extractLsb' 16 16).setWidth 19 + (seq.extractLsb' 0 16).setWidth 19
    + (ack.extractLsb' 16 16).setWidth 19 + (ack.extractLsb' 0 16).setWidth 19 + win.setWidth 19
  let sump : BitVec 21 := (pw.map (·.setWidth 21)).sum
  let tot : BitVec 23 := (0#2 ++ sump) + (0#4 ++ hdr1)
  let f1 : BitVec 17 := (0#1 ++ tot.extractLsb' 0 16) + (0#10 ++ tot.extractLsb' 16 7)
  ~~~ (f1.extractLsb' 0 16 + (0#15 ++ f1.extractLsb' 16 1))

theorem fold16_toNat (x : BitVec 20) : (fold16 x).toNat = canon x.toNat := by
  have e : fold16 x = ocAdd (x.setWidth 16) ((x.ushiftRight 16).setWidth 16) := by
    simp only [fold16, ocAdd]
    bv_decide
  have hx := x.isLt
  simp only [e, ocAdd_toNat, BitVec.toNat_setWidth, toNat_ushr]
  have := canon_fold1 x.toNat (by omega)
  first | exact this | (simpa using this)

theorem ip_step (t i : BitVec 16) :
    (let ip1 : BitVec 17 := (0#1 ++ t) + (0#1 ++ i)
     ip1.extractLsb' 0 16 + (0#15 ++ ip1.extractLsb' 16 1)) = ocAdd t i := by
  simp only [ocAdd]
  bv_decide

theorem fin_t (t : BitVec 23) :
    (let f1 : BitVec 17 := (0#1 ++ t.extractLsb' 0 16) + (0#10 ++ t.extractLsb' 16 7)
     f1.extractLsb' 0 16 + (0#15 ++ f1.extractLsb' 16 1))
    = ocAdd (t.setWidth 16) ((t.ushiftRight 16).setWidth 16) := by
  simp only [ocAdd]
  bv_decide

theorem tcp_core (H : BitVec 19) (S : BitVec 21) :
    (~~~ (let tot : BitVec 23 := (0#2 ++ S) + (0#4 ++ H)
          let f1 : BitVec 17 := (0#1 ++ tot.extractLsb' 0 16) + (0#10 ++ tot.extractLsb' 16 7)
          f1.extractLsb' 0 16 + (0#15 ++ f1.extractLsb' 16 1))).toNat
      = 65535 - canon (S.toNat + H.toNat) := by
  have h1 := S.isLt
  have h2 := H.isLt
  have et : ((0#2 ++ S) + (0#4 ++ H) : BitVec 23) = S.setWidth 23 + H.setWidth 23 := by
    bv_decide
  have ht : ((0#2 ++ S) + (0#4 ++ H) : BitVec 23).toNat = S.toNat + H.toNat := by
    rw [et]
    simp only [BitVec.toNat_add, BitVec.toNat_setWidth]
    omega
  have e := fin_t ((0#2 ++ S) + (0#4 ++ H))
  have hb : S.toNat + H.toNat < 2^23 := by omega
  refine (congrArg (fun x : BitVec 16 => (~~~ x).toNat) e).trans ?_
  try dsimp only
  simp only [BitVec.toNat_not, ocAdd_toNat, BitVec.toNat_setWidth, toNat_ushr, ht]
  rw [canon_fold1 _ hb]
  omega

theorem H_toNat (T sh sl ah al w : BitVec 16) :
    (T.setWidth 19 + sh.setWidth 19 + sl.setWidth 19 + ah.setWidth 19 + al.setWidth 19
      + w.setWidth 19).toNat
    = T.toNat + sh.toNat + sl.toNat + ah.toNat + al.toNat + w.toNat := by
  simp only [BitVec.toNat_add, BitVec.toNat_setWidth]
  have h1 := T.isLt
  have h2 := sh.isLt
  have h3 := sl.isLt
  have h4 := ah.isLt
  have h5 := al.isLt
  have h6 := w.isLt
  omega

theorem sum_bound (l : List (BitVec 16)) : (l.map BitVec.toNat).sum ≤ 65535 * l.length := by
  induction l with
  | nil => simp
  | cons a t ih =>
    have := a.isLt
    simp only [List.map_cons, List.sum_cons, List.length_cons]
    omega

theorem sum21 (l : List (BitVec 16)) (h : l.length ≤ 32) :
    (((l.map (fun x : BitVec 16 => BitVec.setWidth 21 x)).sum : BitVec 21)).toNat
      = (l.map BitVec.toNat).sum := by
  induction l with
  | nil => first | rfl | simp
  | cons a t ih =>
    have hl : t.length ≤ 31 := by
      have h' := h
      simp only [List.length_cons] at h'
      omega
    have ih' := ih (by omega)
    have hb := sum_bound t
    have ha := a.isLt
    simp only [List.map_cons, List.sum_cons]
    rw [BitVec.toNat_add, BitVec.toNat_setWidth, ih']
    omega

theorem tcpTmpl_facts (sip dip : BitVec 32) (sport dport : BitVec 16) (A : Nat)
    (hA : A = (sip.extractLsb' 16 16).toNat + (sip.extractLsb' 0 16).toNat
      + (dip.extractLsb' 16 16).toNat + (dip.extractLsb' 0 16).toNat + 6 + 79
      + sport.toNat + dport.toNat + 20504) :
    (tcpTmpl sip dip sport dport).toNat % 65535 = A % 65535
    ∧ ((tcpTmpl sip dip sport dport).toNat = 0 → A = 0)
    ∧ (A = 0 → (tcpTmpl sip dip sport dport).toNat = 0) := by
  have e : (tcpTmpl sip dip sport dport).toNat = canon A := by
    unfold tcpTmpl
    rw [fold16_toNat]
    refine congrArg canon ?_
    simp only [BitVec.toNat_add, BitVec.toNat_setWidth]
    have b1 := (sip.extractLsb' 16 16).isLt
    have b2 := (sip.extractLsb' 0 16).isLt
    have b3 := (dip.extractLsb' 16 16).isLt
    have b4 := (dip.extractLsb' 0 16).isLt
    have b5 := sport.isLt
    have b6 := dport.isLt
    have c1 : (0x0006#16).toNat = 6 := by first | rfl | decide
    have c2 : (0x004F#16).toNat = 79 := by first | rfl | decide
    have c3 : (0x5018#16).toNat = 20504 := by first | rfl | decide
    omega
  rw [e]
  exact canon_props A

/-! ### The specification: the RTL equals a full recomputation, for all inputs -/

/-- The words of the IPv4 header with the checksum field zero. -/
def ipHeader (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) : List (BitVec 16) :=
  [0x4500, 0x0063, id, 0x4000, ttl ++ 0x06#8, 0, sip.extractLsb' 16 16, sip.extractLsb' 0 16,
   dip.extractLsb' 16 16, dip.extractLsb' 0 16]

/-- S1: the RTL's IPv4 checksum is the Internet checksum of the whole header, for all inputs. -/
theorem rtl_ip_correct (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) :
    rtlIpCsum ttl sip dip id = ~~~ ocSum (ipHeader ttl sip dip id) := by
  have key : ocSum (ipHeader ttl sip dip id) = ocAdd (ipTmpl ttl sip dip) id := by
    apply BitVec.eq_of_toNat_eq
    rw [ocSum_toNat, ocAdd_toNat]
    unfold ipTmpl
    rw [fold16_toNat, canon_canon_add]
    refine congrArg canon ?_
    simp only [ipHeader, List.map_cons, List.map_nil, List.sum_cons, List.sum_nil,
      BitVec.toNat_add, BitVec.toNat_setWidth]
    have b1 := (sip.extractLsb' 16 16).isLt
    have b2 := (sip.extractLsb' 0 16).isLt
    have b3 := (dip.extractLsb' 16 16).isLt
    have b4 := (dip.extractLsb' 0 16).isLt
    have b5 := id.isLt
    have bt : (ttl ++ 0x06#8).toNat < 65536 := by
      have h := (ttl ++ 0x06#8).isLt
      first | omega | exact h | simpa using h
    have hteq : @BitVec.toNat 16 (ttl ++ 0x06#8) = @BitVec.toNat (8+8) (ttl ++ 0x06#8) := rfl
    have k1 : (0x4500#16).toNat = 17664 := by first | rfl | decide
    have k1' : (0x4500 : BitVec 16).toNat = 17664 := by first | rfl | decide
    have k2 : (0x0063#16).toNat = 99 := by first | rfl | decide
    have k2' : (0x0063 : BitVec 16).toNat = 99 := by first | rfl | decide
    have k3 : (0x4000#16).toNat = 16384 := by first | rfl | decide
    have k3' : (0x4000 : BitVec 16).toNat = 16384 := by first | rfl | decide
    have k4 : (0 : BitVec 16).toNat = 0 := by first | rfl | decide
    omega
  have step : rtlIpCsum ttl sip dip id = ~~~ ocAdd (ipTmpl ttl sip dip) id := by
    rw [← ip_step (ipTmpl ttl sip dip) id]
    all_goals try rfl
  rw [step, key]

theorem recv_gen (A B : List (BitVec 16)) :
    ocSum (A ++ (~~~ ocSum (A ++ 0 :: B)) :: B) = 0xFFFF := by
  apply BitVec.eq_of_toNat_eq
  have h0 : (0xFFFF : BitVec 16).toNat = 65535 := by first | rfl | decide
  have z : (0 : BitVec 16).toNat = 0 := by first | rfl | decide
  have h2 := ocSum_toNat (A ++ 0 :: B)
  rw [h0, ocSum_toNat]
  simp only [List.map_append, List.map_cons, List.sum_append, List.sum_cons,
    BitVec.toNat_not, h2, z, Nat.zero_add]
  generalize (A.map BitVec.toNat).sum = a
  generalize (B.map BitVec.toNat).sum = b
  have key : ∀ x, x = a + b + (65535 - canon (a + b)) → canon x = 65535 := by
    intro x hx
    rw [hx]
    exact canon_recv _
  exact key _ (by omega)

/-- S2: the receiver's check passes: the header with the checksum filled in sums to 0xFFFF. -/
theorem rtl_ip_receiver (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) :
    ocSum (ipHeader ttl sip dip id |>.set 5 (rtlIpCsum ttl sip dip id)) = 0xFFFF := by
  have h := recv_gen [0x4500, 0x0063, id, 0x4000, ttl ++ 0x06#8]
    [sip.extractLsb' 16 16, sip.extractLsb' 0 16, dip.extractLsb' 16 16, dip.extractLsb' 0 16]
  rw [rtl_ip_correct]
  exact h

/-- The TCP pseudo-header, header (checksum and urgent pointer zero) and payload words. -/
def tcpWords (sip dip : BitVec 32) (sport dport : BitVec 16) (seq ack : BitVec 32)
    (win : BitVec 16) (pw : List (BitVec 16)) : List (BitVec 16) :=
  [sip.extractLsb' 16 16, sip.extractLsb' 0 16, dip.extractLsb' 16 16, dip.extractLsb' 0 16,
   0x0006, 0x004F, sport, dport, seq.extractLsb' 16 16, seq.extractLsb' 0 16,
   ack.extractLsb' 16 16, ack.extractLsb' 0 16, 0x5018, win, 0, 0] ++ pw

/-- S3: the RTL's TCP checksum is the Internet checksum of pseudo-header, header and payload,
    for all addresses, ports, sequence numbers, windows and payloads of at most 30 words
    (the RTL's payload sum register is 21 bits, enough for up to 32). -/
theorem rtl_tcp_correct (sip dip : BitVec 32) (sport dport : BitVec 16) (seq ack : BitVec 32)
    (win : BitVec 16) (pw : List (BitVec 16)) (h : pw.length ≤ 30) :
    rtlTcpCsum sip dip sport dport seq ack win pw
      = ~~~ ocSum (tcpWords sip dip sport dport seq ack win pw) := by
  have hS : (((pw.map (fun x : BitVec 16 => BitVec.setWidth 21 x)).sum : BitVec 21)).toNat
      = (pw.map BitVec.toNat).sum :=
    sum21 pw (by omega)
  have hP := sum_bound pw
  have core := tcp_core
    ((tcpTmpl sip dip sport dport).setWidth 19
      + (seq.extractLsb' 16 16).setWidth 19 + (seq.extractLsb' 0 16).setWidth 19
      + (ack.extractLsb' 16 16).setWidth 19 + (ack.extractLsb' 0 16).setWidth 19
      + win.setWidth 19 : BitVec 19)
    ((pw.map (fun x : BitVec 16 => BitVec.setWidth 21 x)).sum)
  rw [H_toNat, hS] at core
  obtain ⟨hT1, hT2, hT3⟩ := tcpTmpl_facts sip dip sport dport _ rfl
  apply BitVec.eq_of_toNat_eq
  refine core.trans ?_
  clear core
  rw [BitVec.toNat_not, ocSum_toNat]
  simp only [tcpWords, List.map_append, List.map_cons, List.map_nil, List.sum_append,
    List.sum_cons, List.sum_nil]
  have c1 : (0x0006 : BitVec 16).toNat = 6 := by first | rfl | decide
  have c2 : (0x004F : BitVec 16).toNat = 79 := by first | rfl | decide
  have c3 : (0x5018 : BitVec 16).toNat = 20504 := by first | rfl | decide
  have c4 : (0 : BitVec 16).toNat = 0 := by first | rfl | decide
  have e16 : (2:Nat)^16 - 1 = 65535 := by omega
  first | rw [e16] | skip
  refine congrArg (fun z : Nat => 65535 - z) ?_
  apply canon_congr
  all_goals (intros; omega)

/-! ### RFC 1624, equation 3: updating a checksum after one field changes -/

/-- Incremental update `HC' = ~(~HC + ~m + m')` (RFC 1624 eqn 3). -/
def incUpdate (hc m m' : BitVec 16) : BitVec 16 := ~~~ (ocAdd (ocAdd (~~~hc) (~~~m)) m')

theorem ocSum_snoc (l : List (BitVec 16)) (x : BitVec 16) :
    ocSum (l ++ [x]) = ocAdd (ocSum l) x := by
  unfold ocSum
  simp [List.foldl_append]

/-- S4: updating the checksum of a header (any length) after word `m` becomes `m'` gives the
    checksum of the recomputed header, provided the new header is not all zero words. -/
theorem incUpdate_correct (l : List (BitVec 16)) (m m' : BitVec 16)
    (h : ocSum (l ++ [m']) ≠ 0) :
    incUpdate (~~~ ocSum (l ++ [m])) m m' = ~~~ ocSum (l ++ [m']) := by
  have e1 := ocSum_snoc l m
  have e2 := ocSum_snoc l m'
  rw [e2] at h
  rw [e1, e2]
  unfold incUpdate
  simp only [BitVec.not_not]
  refine congrArg (fun x : BitVec 16 => ~~~ x) ?_
  have ha : (ocSum l).toNat ≤ 65535 := by
    have := (ocSum l).isLt
    omega
  have hm : m.toNat ≤ 65535 := by
    have := m.isLt
    omega
  have hm' : m'.toNat ≤ 65535 := by
    have := m'.isLt
    omega
  have hne : (ocSum l).toNat + m'.toNat ≠ 0 := by
    intro h0
    apply h
    apply BitVec.eq_of_toNat_eq
    rw [ocAdd_toNat, h0]
    all_goals first | rfl | decide
  apply BitVec.eq_of_toNat_eq
  simp only [ocAdd_toNat, BitVec.toNat_not]
  exact canon_inc _ _ _ ha hm hm' hne

/-- S4 needs its side condition: for an all-zero header the update gives 0x0000, not 0xFFFF. -/
theorem incUpdate_zero_corner :
    incUpdate (~~~ ocSum ([] ++ [(0 : BitVec 16)])) 0 0 ≠ ~~~ ocSum ([] ++ [(0 : BitVec 16)]) := by
  first
    | decide
    | (unfold incUpdate ocSum ocAdd; bv_decide)
    | (simp [incUpdate, ocSum, ocAdd])

end Cksum
