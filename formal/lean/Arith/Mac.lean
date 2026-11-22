/-
  Specification file for brief 139a: the accumulator of arith/mac/rtl/mac_dsp.sv, mac_dsp_cascade.sv and mac_fabric.sv, for every run length and width.

  The definitions and the theorem statements in this file are the SPECIFICATION, LEFT FOR THE OWNER'S APPROVAL (arith/mac/verif/lean_approvals.yaml has
  no entry: every statement shows "statement not approved").

  What is modelled. The accumulator holds a natural number below M = 2^ACCW. One clock with a sample present is
  `step M acc clr p = ((if clr then 0 else acc) + p) % M`, where p is the sample's lane sum already reduced to a natural number modulo M (a negative
  product is its two's-complement value modulo M, which is how the RTL sign-extends it into the accumulator); a clock without a sample leaves acc as it is
  and is not a step. `run` applies a list of samples in order. `run_noclr` says that a run with no clr adds up: acc0 plus the sum of the products,
  reduced modulo M, however long the run; `run_after_clr` says that a clr makes the history irrelevant: whatever acc was, a clr sample followed by
  clr-free samples gives that sample's product plus the others, reduced modulo M. Together: acc is always the sum of the products since the last
  clr, modulo 2^ACCW, which is the "exact modulo 2^ACCW, no saturation" claim of arith/mac/spec.md for every run length. NOT modelled: the lane
  products (arith/multiplier covers them), the pipeline latency and skew (a delay of the sample sequence), reset, and the enable. The Lean text is a hand
  transcription of the RTL's `acc <= (clr ? 0 : acc) + sum` line, tested only through simulation and bounded SymbiYosys checks of the RTL.
-/
namespace ArithMac

/-- One accumulate clock with a sample: restart on clr, add, wrap modulo M. -/
def step (M acc : Nat) (clr : Bool) (p : Nat) : Nat := ((if clr then 0 else acc) + p) % M

/-- A run of samples (clr flag, product) applied in order from an initial accumulator value. -/
def run (M : Nat) : Nat → List (Bool × Nat) → Nat
  | acc, [] => acc
  | acc, (c, p) :: r => run M (step M acc c p) r

theorem run_noclr (M acc0 : Nat) (hM : 0 < M) (h0 : acc0 < M) (ps : List Nat) :
    run M acc0 (ps.map (fun p => (false, p))) = (acc0 + ps.sum) % M := by
  induction ps generalizing acc0 with
  | nil => simp [run, Nat.mod_eq_of_lt h0]
  | cons p r ih =>
    have hlt : (acc0 + p) % M < M := Nat.mod_lt _ hM
    have h := ih ((acc0 + p) % M) hlt
    simp only [List.map_cons, run, step, List.sum_cons, Bool.false_eq_true, ite_false]
    rw [h, Nat.mod_add_mod, Nat.add_assoc]

theorem run_after_clr (M acc p : Nat) (hM : 0 < M) (ps : List Nat) :
    run M acc ((true, p) :: ps.map (fun q => (false, q))) = (p + ps.sum) % M := by
  have hlt : (0 + p) % M < M := Nat.mod_lt _ hM
  simp only [run, step, ite_true]
  rw [run_noclr M ((0 + p) % M) hM hlt ps, Nat.mod_add_mod, Nat.zero_add]

end ArithMac
