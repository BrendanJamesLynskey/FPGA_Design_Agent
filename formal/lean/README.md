# Lean 4 proofs about the checksum arithmetic of brief 119's TCP fast path (brief 124)

A small Lean 4 project (core library only, no Mathlib) that proves, for **all** inputs and all payload lengths, that the checksum equations of
`designs/b119_tcp_fast/rtl/tcp_fast.sv` compute the Internet checksum (RFC 1071) of the whole IPv4 header and TCP segment, and that the
incremental update rule of RFC 1624 equation 3 is correct for headers of any length. The proofs were written by a model (Claude Sonnet 5.5)
against statements written for it and checked by Lean's kernel. The assessment that this belongs to is [docs/lean_assessment.md](../../docs/lean_assessment.md); the run records are
in [results/124_lean](../../results/124_lean/README.md). SymbiYosys and simulation remain the tools for control logic and per-width checks.

## What is proved

`Cksum/Spec.lean` holds the definitions, the transcription of the RTL equations and the theorems. The statements are the specification.

| Theorem | Statement (in words) | Tier |
|---|---|---|
| `ocSum_toNat` | for a list of 16-bit words of any length, the ones' complement sum equals the natural-number sum reduced mod 65535 (0 kept for an empty or all-zero list) | kernel only |
| `rtl_ip_correct` | for all TTL, addresses and identification values, the RTL's `ipcsum` equals the complement of the ones' complement sum of the ten header words | uses `bv_decide` |
| `rtl_ip_receiver` | the header with that checksum filled in sums to 0xFFFF (the receiver's check passes) | uses `bv_decide` |
| `rtl_tcp_correct` | for all addresses, ports, sequence and acknowledgement numbers, windows and payloads of up to 30 words, the RTL's `csum` equals the complement of the sum over pseudo-header, header and payload | uses `bv_decide` |
| `incUpdate_correct` | RFC 1624 equation 3 gives the checksum of the recomputed header, for a header of any length, provided the new header is not all zero words | kernel only |
| `incUpdate_zero_corner` | the side condition is needed: for an all-zero header the update gives 0x0000, not 0xFFFF | kernel only |

Tiers (computed by `tools/lean_evidence.py` from `#print axioms`, never typed): **kernel only** means the proof depends on no axiom beyond `propext`,
`Classical.choice` and `Quot.sound`. **Uses `bv_decide`** means three small 16-to-23-bit lemmas (`fold16_toNat`, `ip_step`, `fin_t`) are proved by the
`bv_decide` tactic, which hands a bit-vector goal to a SAT solver and checks the solver's certificate with compiled code; each adds an axiom named
`<lemma>._native.bv_decide.ax_*`, so the Lean compiler joins the trusted base for those lemmas. The statements are exactly the same either way.

The RTL's template step is not RFC 1624's update: the RTL keeps partial sums of the fixed header words and adds the changing fields per order, folding at the end.
`rtl_ip_correct` and `rtl_tcp_correct` prove that this equals recomputing the whole checksum. `incUpdate_correct` proves the general update rule for a future design that
patches a checksum in place; no current RTL uses it.

## Records

- Files: `Cksum/Spec.lean` (the proved file), `Cksum/CrossCheck.lean` (600 `#guard` checks, generated), `tools/statements.py` (statement-integrity check),
  `tools/llm_prove.py` (the model loop, through `agent.models.resolver_for`), `tools/lean_evidence.py` (the evidence record), `tools/crosscheck_b119.py` (the generator of `CrossCheck.lean`).
- The model's first try failed to build (27 errors); four rounds of checker feedback produced a file that builds with the statements unchanged. Details: [results/124_lean/README.md](../../results/124_lean/README.md).
- Lean 4.36.0 (`lean-toolchain`), `lake build` takes about 6 s for `Spec.lean` and about 11 s for the cross-check.
- Evidence record: [results/124_lean/lean_evidence.json](../../results/124_lean/lean_evidence.json), status per theorem from the real build.

## How the RTL is linked, and how honestly

1. **Transcription (manual).** `fold16`, `ipTmpl`, `rtlIpCsum`, `tcpTmpl` and `rtlTcpCsum` in `Spec.lean` are written by hand from the lines of `tcp_fast.sv` named in their comments,
   at commit `9f8d760788e4a8afcd8756e29eca348d49858765` of branch `b119-tcp-fast` (template build lines 256-260, per-order sums lines 326-336), keeping every register width (17, 19, 20, 21 and 23 bits). No tool generates them. A human must read them
   against the RTL: that reading is the link, and it is as strong as that reading.
2. **Cross-check against brief 119's Python reference.** `Cksum/CrossCheck.lean` compares the transcribed equations with the checksum fields of real frames built by `model/tcpref.py` for 300 random
   connections and orders (600 `#guard` lines). 119's cocotb tests compare that reference with the RTL, so the chain is: RTL, 119's tests, Python reference, this check, Lean transcription. It is a test, not a proof, and covers 300 samples.
3. **Not covered.** The payload sum is taken over a list of 16-bit words (the RTL's byte-pair swapping in `gsum` and the streaming check `sumerr` are not modelled); the pipeline timing (which edge each value is ready) is not modelled; the
   control logic is not modelled. The proofs say: whatever the registers hold at the end, the arithmetic is right.

## Reproduce

```
export PATH=$HOME/.elan/bin:$PATH                   # elan installs Lean 4.36.0 from lean-toolchain on first use
cd formal/lean && lake build
python3 -I tools/lean_evidence.py                   # evidence record from the build
python3 -I tools/statements.py <approved Spec.lean> Cksum/Spec.lean   # the statements are unchanged
python3 tools/crosscheck_b119.py --b119 <checkout of b119-tcp-fast>/designs/b119_tcp_fast   # regenerate CrossCheck.lean
```

## Known gaps and limits

- The statements were written for the model by the executor of brief 124, not approved by the owner; the specification is exactly the part a human must check. The two things to read are the RTL transcription and the theorem statements.
- Kernel-only proofs of the three `bv_decide` lemmas were not achieved by the model in six rounds (the model invented a lemma name `BitVec.toNat_extractLsb'` and fell back to `bv_decide` whenever it was not shown a Lean error). A tool-using agent that can run `#check` and `exact?` would likely close this; not tried.
- Lean is not in CI: the toolchain is about 3 GB installed and the download is not a few minutes' job. The build itself takes under half a minute once it is installed.
- `canon`'s 0 versus 0xFFFF convention is the one RFC 1071's loop gives from an initial 0; a receiver that treats 0x0000 and 0xFFFF as equal is not affected, and the RFC 1624 corner is the all-zero header.
- Brief 124 proved only checksums; brief 125 added the gray-code lemma (next section).
- The Lean model is not the RTL: a mismatch between them is invisible to Lean.

## Gray code, for every width (brief 125)

`Gray/Spec.lean` holds the encoder and decoder of AMD's `xpm_cdc_gray` as the repository's behavioural model writes them (`flow/cdc_models/xpm_cdc_models.sv`, lines 71-87) and four theorems, each for every
width `n > 0` (`gray_step` includes the wrap from 2^n - 1 to 0):

| Theorem | Statement (in words) | Tier |
|---|---|---|
| `gray_step` | the gray codes of `b` and `b + 1` differ in exactly one bit | kernel only |
| `gray2bin_bin2gray` | decoding the encoding of `b` gives `b` | kernel only |
| `bin2gray_gray2bin` | encoding the decoding of `g` gives `g` | kernel only |
| `gray_sample` | a code that is the old or the new code of a step decodes to the old or the new count | kernel only |

`designs/b96_kr260_10g/rtl/rate_match_gp.sv` crosses both of its pointers (binary counters of `AW + 1` bits, modulo 2^(AW+1)) through `xpm_cdc_gray` (lines 78-82). The link is **a transcription of the
repository's model of the macro, tested**: `Gray/CrossCheck.lean` (generated by `tools/crosscheck_gray.py`) has 1020 `#guard` lines comparing the Lean encoder and decoder with that model run in Icarus Verilog, every value of widths 1 to 8. Neither the
model nor Lean says anything about AMD's own macro beyond its documented behaviour (UG974), and nothing here models the synchroniser flops, the clocks or metastability.
**The statements are for the owner's approval; none is approved.** The proofs were written by Claude Sonnet 5.5 through the proof driver (`tools/prove.py`, purpose `proof` of the 108 table): the first try did not build (one unsolved goal), the
second round did; all four are kernel only. Records: [results/125_lean](../../results/125_lean/README.md).

## How it enters the traceability matrix (brief 125)

`python -m flow.trace_v1 lean-record` runs `lake build` here and writes `records/build_record.json` (file hashes, each theorem's axioms and tier, the transcribed RTL lines' hashes). The v1 testplan's `formal_lean`
items (for example in `designs/b96_kr260_10g/verif/testplan.yaml` for the gray code and `designs/b119_tcp_fast/verif/testplan.yaml` for the checksums) name a theorem and how it meets the RTL; the matrix reads the record when Lean is not installed and shows "recorded build (not re-run)". Re-run `lean-record` and
commit the record after any change to a `.lean` file, the lakefile or a transcribed RTL line, or the items go stale. See [docs/traceability_v1.md](../../docs/traceability_v1.md#lean-proofs-formal_lean-brief-125).

```
python3 formal/lean/tools/prove.py --module Gray.Spec --theorem <name> [--theorem <name> ...] --out <dir>   # the proof driver: a model writes the proof, lake build feeds back, statements frozen
python3 formal/lean/tools/crosscheck_gray.py                                                               # regenerate Gray/CrossCheck.lean from the Verilog model
python -m flow.trace_v1 lean-record                                                                        # rebuild and write the hash-pinned build record
python -m flow.trace_v1 lean-statement designs/b96_kr260_10g V-LEAN-GRAY-STEP                              # the statement and hashes a human reads before approving
```
