/-
  Specification file for brief 124. The definitions and theorem statements in this file are
  the SPECIFICATION: they are written and approved by a human and must not be changed by the
  proof writer. Proofs live in Cksum/Proofs.lean and may only fill in the proof of each
  theorem with the same name and statement.

  Source of the RTL equations: designs/b119_tcp_fast/rtl/tcp_fast.sv, branch b119-tcp-fast,
  commit 9f8d760788e4a8afcd8756e29eca348d49858765 (fold16 at line 166, template build at
  lines 258-261, per-order sums at lines 327-336). The transcription below is MANUAL.
-/
namespace Cksum

/-- Ones' complement addition of two 16-bit words (RFC 1071: add, then add the carry back). -/
def ocAdd (a b : BitVec 16) : BitVec 16 :=
  let s : BitVec 17 := a.setWidth 17 + b.setWidth 17
  s.setWidth 16 + (s.ushiftRight 16).setWidth 16

/-- The Internet checksum sum of a list of 16-bit words (before the final complement). -/
def ocSum (l : List (BitVec 16)) : BitVec 16 := l.foldl ocAdd 0

/-- The value an end-around-carry sum has: n mod 65535, with 0 kept for n = 0 and 65535 for the
    other multiples of 65535 (the representation RFC 1071 produces from a start of 0). -/
def canon (n : Nat) : Nat := if n = 0 then 0 else (n - 1) % 65535 + 1

/-- Mathematical meaning of the ones' complement sum, for lists of any length. -/
theorem ocSum_toNat (l : List (BitVec 16)) :
    (ocSum l).toNat = canon ((l.map BitVec.toNat).sum) := by
  sorry

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

/-! ### The specification: the RTL equals a full recomputation, for all inputs -/

/-- The words of the IPv4 header with the checksum field zero. -/
def ipHeader (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) : List (BitVec 16) :=
  [0x4500, 0x0063, id, 0x4000, ttl ++ 0x06#8, 0, sip.extractLsb' 16 16, sip.extractLsb' 0 16,
   dip.extractLsb' 16 16, dip.extractLsb' 0 16]

/-- S1: the RTL's IPv4 checksum is the Internet checksum of the whole header, for all inputs. -/
theorem rtl_ip_correct (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) :
    rtlIpCsum ttl sip dip id = ~~~ ocSum (ipHeader ttl sip dip id) := by
  sorry

/-- S2: the receiver's check passes: the header with the checksum filled in sums to 0xFFFF. -/
theorem rtl_ip_receiver (ttl : BitVec 8) (sip dip : BitVec 32) (id : BitVec 16) :
    ocSum (ipHeader ttl sip dip id |>.set 5 (rtlIpCsum ttl sip dip id)) = 0xFFFF := by
  sorry

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
  sorry

/-! ### RFC 1624, equation 3: updating a checksum after one field changes -/

/-- Incremental update `HC' = ~(~HC + ~m + m')` (RFC 1624 eqn 3). -/
def incUpdate (hc m m' : BitVec 16) : BitVec 16 := ~~~ (ocAdd (ocAdd (~~~hc) (~~~m)) m')

/-- S4: updating the checksum of a header (any length) after word `m` becomes `m'` gives the
    checksum of the recomputed header, provided the new header is not all zero words. -/
theorem incUpdate_correct (l : List (BitVec 16)) (m m' : BitVec 16)
    (h : ocSum (l ++ [m']) ≠ 0) :
    incUpdate (~~~ ocSum (l ++ [m])) m m' = ~~~ ocSum (l ++ [m']) := by
  sorry

/-- S4 needs its side condition: for an all-zero header the update gives 0x0000, not 0xFFFF. -/
theorem incUpdate_zero_corner :
    incUpdate (~~~ ocSum ([] ++ [(0 : BitVec 16)])) 0 0 ≠ ~~~ ocSum ([] ++ [(0 : BitVec 16)]) := by
  sorry

end Cksum
