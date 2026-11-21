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

/-- req: B96-F-LEAN-GRAY-STEP
    For every width `n > 0` and every counter value `b`, the gray codes of `b` and of `b + 1` (the counter
    steps by one and wraps from 2^n - 1 to 0) differ in exactly one bit. -/
theorem gray_step {n : Nat} (hn : 0 < n) (b : BitVec n) :
    ∃ i : Fin n, ∀ j : Fin n,
      ((bin2gray b).getLsbD j.val ≠ (bin2gray (b + 1)).getLsbD j.val) ↔ j = i := by
  sorry

/-- req: B96-F-LEAN-GRAY-DECODE
    For every width and every binary value, the decoder inverts the encoder. -/
theorem gray2bin_bin2gray {n : Nat} (b : BitVec n) : gray2bin (bin2gray b) = b := by
  sorry

/-- req: B96-F-LEAN-GRAY-DECODE
    For every width and every gray value, the encoder inverts the decoder (so the two are a bijection). -/
theorem bin2gray_gray2bin {n : Nat} (g : BitVec n) : bin2gray (gray2bin g) = g := by
  sorry

/-- req: B96-F-LEAN-GRAY-DECODE
    A sampled gray value that is the code of the old count or of the new count decodes to the old or the new count,
    for every width and every count (the property the pointer crossing relies on). -/
theorem gray_sample {n : Nat} (hn : 0 < n) (b g : BitVec n)
    (h : g = bin2gray b ∨ g = bin2gray (b + 1)) : gray2bin g = b ∨ gray2bin g = b + 1 := by
  sorry

end Gray
