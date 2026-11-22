"""Seeded faults of the phase 1 functions of the frequency-domain suite (arith brief 161); merged into the list of gen_mutants_fft.py.

(name, variant, class, file or None, old, new, why): each `old` occurs exactly once in the file (the variant's own, or `file` relative to the function's folder)."""
from __future__ import annotations

OUT = "../fft_common/fft_bfp_out.sv"
M_P1: dict[str, list[tuple]] = {
    "fft_bfp": [
        ("exp_off", "sdf", "constant", OUT, "sh_new = EW'(bl + 1 - W);", "sh_new = EW'(bl - W);", "the exponent is one too small: the largest part does not fit"),
        ("bl_off", "sdf", "constant", OUT, "if (acc_sel[i]) bl = i + 1;", "if (acc_sel[i]) bl = i;", "the bit length is one too small"),
        ("mag_not_xored", "sdf", "operator", OUT, "mr       = in_re ^ {WC{in_re[WC-1]}};", "mr       = in_re;", "negative real parts are not turned into their ones-complement magnitude: the OR sees the sign bits"),
        ("imag_ignored", "sdf", "connection", OUT, "acc_n    = (in_sof ? '0 : acc) | mr | mi;", "acc_n    = (in_sof ? '0 : acc) | mr;", "the imaginary parts do not enter the exponent"),
        ("acc_not_restarted", "sdf", "connection", OUT, "acc_n    = (in_sof ? '0 : acc) | mr | mi;", "acc_n    = acc | mr | mi;", "the OR is not cleared at a frame start: the largest earlier frame sets this one's exponent"),
        ("round_inverted", "sdf", "operator", OUT, "if (RND != 0 && shr > 0) t", "if (RND == 0 && shr > 0) t", "the rounding constant is added in the truncating mode and not in the rounding mode"),
        ("round_half_off", "sdf", "constant", OUT, "t = t + (WN'(1) <<< (shr - 1));", "t = t + (WN'(1) <<< shr);", "the rounding constant is a whole unit, not a half"),
        ("saturation_to_zero", "sdf", "constant", OUT, "t = WN'((1 <<< (W - 1)) - 1);\n        return", "t = '0;\n        return", "a part that the rounding carries to 2**(W-1) becomes zero instead of saturating"),
        ("left_shift_zero_ext", "sdf", "width", OUT, "t   = WN'(x) <<< shl;", "t   = WN'($unsigned(x)) <<< shl;", "a negative word is zero-extended before the shift"),
        ("acc_bank", "sdf", "connection", OUT, "acc_sel = rb ? acc1 : acc0;", "acc_sel = rb ? acc0 : acc1;", "the exponent is taken from the other bank's OR"),
        ("bank_not_toggled", "sdf", "connection", OUT, "wb <= ~wb;", "wb <= wb;", "the write bank never changes: a frame overwrites the one before it"),
        ("full_clear_other", "sdf", "connection", OUT, "if (rb) full1 <= 1'b0; else full0 <= 1'b0;", "if (rb) full0 <= 1'b0; else full1 <= 1'b0;", "the wrong bank is released"),
        ("order_swapped", "sdf", "connection", OUT, "ridx    = (ORDER == 0) ? rbr : idx;", "ridx    = (ORDER == 0) ? idx : rbr;", "natural and bit-reversed output order exchanged"),
        ("sof_on_last", "sdf", "constant", OUT, "s1      <= issue && first;", "s1      <= issue && rlast;", "out_sof marks the last word"),
        ("exp_not_aligned", "sdf", "latency", OUT, "out_exp <= e1;", "out_exp <= sh_new;", "the exponent is two clocks ahead of the data (visible when frames follow each other with different levels)"),
        ("exp_zero", "sdf", "connection", OUT, "out_exp <= e1;", "out_exp <= '0;", "the exponent output is not driven"),
        ("core_scaled", "sdf", "constant", None, ".SCALE(0), .RND(RND), .ORDER(1)", ".SCALE(1), .RND(RND), .ORDER(1)", "the core runs scaled: the output is 1/N of the unscaled transform in the wide words"),
        ("core_natural", "sdf", "constant", None, ".SCALE(0), .RND(RND), .ORDER(1)", ".SCALE(0), .RND(RND), .ORDER(0)", "the core reorders to natural order and the store reads bit-reversed: the order is scrambled"),
        ("hold_missing", "burst", "connection", OUT, "en      = !(ov && !out_ready);", "en      = 1'b1;", "the read-out does not stall: words are lost while the sink is not ready"),
        ("rd_not_held", "burst", "connection", OUT, "if (en) rd <= mem[{rb, ridx}];", "rd <= mem[{rb, ridx}];", "the memory output register is not held while the output is stalled"),
        ("exp_not_held", "burst", "connection", OUT, "if (en) e1 <= sh_new;", "e1 <= sh_new;", "the exponent pipeline register is not held while the output is stalled"),
        ("wr_always_ready", "burst", "connection", OUT, "wr_ready = wb ? !full1 : !full0;", "wr_ready = 1'b1;", "the core is never held back: a frame overwrites a bank that is still being read"),
        ("core_not_stalled", "burst", "connection", None, ".out_ready(wr_ready)", ".out_ready(1'b1)", "the core's output is never stalled by the full frame store"),
    ],
}
EQ_P1 = {
    "fft_bfp": ["`wpos = wcnt` instead of `in_sof ? 0 : wcnt` in fft_bfp_out: the write counter wraps at N, so for the contiguous frames of exactly N words that both cores deliver it equals the restarted counter (the OR accumulator does restart at in_sof: mutant acc_not_restarted)",
                "`bl = i + 1` guarded by `i < WC - 1`: bit WC - 1 of the OR is the sign of the XORed magnitude, always 0, so the guard never changes the result"],
}
