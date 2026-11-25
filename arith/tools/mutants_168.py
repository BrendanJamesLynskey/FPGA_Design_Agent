"""Seeded faults of fft_mdc2_axis (arith brief 168); merged into the list of gen_mutants_fft.py.

(name, variant, class, file or None, old, new, why): each `old` occurs exactly once in the file (the variant's own, or `file` relative to the function's folder)."""
from __future__ import annotations

OUT = "../fft_common/fft_bfp_out_pair.sv"
CTL = "rtl/fft_mdc2_axis_ctl.sv"
READY = "s_ready = at_start ? ((gap == '0) && (infl != CW'(NB))) : 1'b1;"
M_168: dict[str, list[tuple]] = {
    "fft_mdc2_axis": [
        # ---- slave-side control: the gap window, the gap counter, the credit
        ("gap_rule_removed", "par2", "operator", CTL, READY, "s_ready = at_start ? (1'b1 && (infl != CW'(NB))) : 1'b1;", "the frame gap is not enforced: a source that idles 1 to N/8 - 1 clocks corrupts a frame"),
        ("gap_one_short", "par2", "constant", CTL, "gap <= LOGN'(GAP - 1);", "gap <= LOGN'(GAP - 2);", "tready returns one clock early: N/8 - 1 idle clocks"),
        ("gap_one_long", "par2", "constant", CTL, "gap <= LOGN'(GAP - 1);", "gap <= LOGN'(GAP);", "tready returns one clock late: N/8 + 1 idle clocks (correct data, throughput lost)"),
        ("credit_ignored", "par2", "operator", CTL, READY, "s_ready = at_start ? ((gap == '0) && 1'b1) : 1'b1;", "frames are accepted although every bank may be in use: the store overflows when the sink stalls"),
        ("credit_one_too_many", "par2", "constant", CTL, READY, "s_ready = at_start ? ((gap == '0) && (infl != CW'(NB + 1))) : 1'b1;", "NB + 1 frames are allowed in the block"),
        ("credit_one_too_few", "par2", "constant", CTL, READY, "s_ready = at_start ? ((gap == '0) && (infl != CW'(NB - 1))) : 1'b1;", "only NB - 1 frames are allowed in the block (correct data, throughput lost)"),
        ("credit_never_returned", "par2", "connection", CTL, "else if (done && !up) infl <= infl - 1'b1;", "else if (done && !up) infl <= infl;", "a finished frame does not give its credit back: the block stops after NB frames"),
        ("credit_every_beat", "par2", "operator", CTL, "up      = xfer && at_start;", "up      = xfer;", "every input beat takes a credit, not only the first of a frame"),
        ("start_polarity", "par2", "operator", CTL, "at_start <= s_last;", "at_start <= !s_last;", "the start flag follows the wrong polarity of tlast"),
        # ---- the wrapper
        ("direction_ignored", "par2", "connection", None, ".in_inverse(s_axis_tuser[0])", ".in_inverse(1'b0)", "tuser of the input is not read: every frame is forward"),
        ("sof_always", "par2", "connection", None, ".in_sof(at_start)", ".in_sof(1'b1)", "every beat is a start of frame"),
        ("core_sees_unaccepted", "par2", "operator", None, "in_valid = s_axis_tvalid && s_axis_tready;", "in_valid = s_axis_tvalid;", "beats are taken that were not accepted (tready low)"),
        ("odd_sample_exchanged", "par2", "connection", None, ".in_re1(s_axis_tdata[3*W-1:2*W]), .in_im1(s_axis_tdata[4*W-1:3*W])", ".in_re1(s_axis_tdata[4*W-1:3*W]), .in_im1(s_axis_tdata[3*W-1:2*W])", "real and imaginary part of the odd sample exchanged on the input"),
        ("even_odd_exchanged", "par2", "connection", None, ".in_re0(s_axis_tdata[W-1:0]), .in_im0(s_axis_tdata[2*W-1:W]), .in_re1(s_axis_tdata[3*W-1:2*W])", ".in_re0(s_axis_tdata[3*W-1:2*W]), .in_im0(s_axis_tdata[4*W-1:3*W]), .in_re1(s_axis_tdata[W-1:0])", "the even and the odd sample exchanged on the input"),
        ("done_ignores_ready", "par2", "operator", None, "done     = o_valid && m_axis_tready && o_last;", "done     = o_valid && o_last;", "a frame gives its credit back when its last beat is offered, not when it is taken: a stalled sink overflows the store"),
        ("core_scaled", "par2", "constant", None, ".SCALE(0), .RND(RND), .ORDER(1)", ".SCALE(1), .RND(RND), .ORDER(1)", "the core runs scaled: the output is 1/N of the unscaled transform in the wide words"),
        ("core_natural", "par2", "constant", None, ".SCALE(0), .RND(RND), .ORDER(1)", ".SCALE(0), .RND(RND), .ORDER(0)", "the core reorders to natural order and the store reads bit-reversed: the order is scrambled"),
        ("pack_out", "par2", "connection", None, "m_axis_tdata  = {o_im1, o_re1, o_im0, o_re0};", "m_axis_tdata  = {o_im0, o_re0, o_im1, o_re1};", "the two samples of an output beat exchanged"),
        ("part_out", "par2", "connection", None, "m_axis_tdata  = {o_im1, o_re1, o_im0, o_re0};", "m_axis_tdata  = {o_re1, o_im1, o_re0, o_im0};", "real and imaginary parts exchanged on the output"),
        ("tuser_zero", "par2", "connection", None, "m_axis_tuser  = o_exp;", "m_axis_tuser  = '0;", "the exponent is not driven on tuser"),
        # ---- the frame store with the exponent
        ("exp_off", "par2", "constant", OUT, "sh_new = EW'(bl + 1 - W);", "sh_new = EW'(bl - W);", "the exponent is one too small: the largest part does not fit"),
        ("bl_off", "par2", "constant", OUT, "if (acc_sel[i]) bl = i + 1;", "if (acc_sel[i]) bl = i;", "the bit length is one too small"),
        ("mag_not_xored", "par2", "operator", OUT, "acc_n = (in_sof ? '0 : acc) | (in_re0 ^ {WC{in_re0[WC-1]}})", "acc_n = (in_sof ? '0 : acc) | (in_re0)", "negative real parts of the even sample are not turned into their ones-complement magnitude: the OR sees the sign bits"),
        ("odd_imag_ignored", "par2", "connection", OUT, " | (in_im1 ^ {WC{in_im1[WC-1]}});", ";", "the odd sample's imaginary part does not enter the exponent"),
        ("acc_not_restarted", "par2", "connection", OUT, "acc_n = (in_sof ? '0 : acc) |", "acc_n = acc |", "the OR is not cleared at a frame start: the largest earlier frame sets this one's exponent"),
        ("round_inverted", "par2", "operator", OUT, "if (RND != 0 && shr > 0) t", "if (RND == 0 && shr > 0) t", "the rounding constant is added in the truncating mode and not in the rounding mode"),
        ("round_half_off", "par2", "constant", OUT, "t = t + (WN'(1) <<< (shr - 1));", "t = t + (WN'(1) <<< shr);", "the rounding constant is a whole unit, not a half"),
        ("saturation_to_zero", "par2", "constant", OUT, "t = WN'((1 <<< (W - 1)) - 1);\n        return", "t = '0;\n        return", "a part that the rounding carries to 2**(W-1) becomes zero instead of saturating"),
        ("left_shift_zero_ext", "par2", "width", OUT, "t   = WN'(x) <<< shl;", "t   = WN'($unsigned(x)) <<< shl;", "a negative word is zero-extended before the shift"),
        ("acc_bank", "par2", "connection", OUT, "acc_sel = accs[rb];", "acc_sel = accs[wb];", "the exponent is taken from the OR of the bank being written, not the one being read"),
        ("write_bank_stuck", "par2", "connection", OUT, "wb       <= (wb == BW'(NB - 1)) ? '0 : wb + 1'b1;", "wb       <= wb;", "the write bank never changes: a frame overwrites the one before it"),
        ("read_bank_stuck", "par2", "connection", OUT, "rb       <= (rb == BW'(NB - 1)) ? '0 : rb + 1'b1;", "rb       <= rb;", "the read bank never changes: the first frame's bank is read again"),
        ("bank_wrap_early", "par2", "constant", OUT, "wb       <= (wb == BW'(NB - 1)) ? '0 : wb + 1'b1;", "wb       <= (wb == BW'(NB - 2)) ? '0 : wb + 1'b1;", "the write bank wraps one bank early: the last bank is never used"),
        ("mem_banks_overlap", "par2", "connection", OUT, "mem[int'(wb) * H + int'(wpos)] <=", "mem[int'(wpos)] <=", "every frame is written into the first bank's addresses"),
        ("read_bank_zero", "par2", "connection", OUT, "if (en) rd <= mem[int'(rb) * H + int'(ridx)];", "if (en) rd <= mem[int'(ridx)];", "every frame is read from the first bank's addresses"),
        ("order_unreversed", "par2", "connection", OUT, "ridx    = rbr;", "ridx    = idx;", "the pair index is not bit reversed on reading: bit-reversed order out"),
        ("pair_written_swapped", "par2", "connection", OUT, "{in_re0, in_im0, in_re1, in_im1};", "{in_re1, in_im1, in_re0, in_im0};", "the two samples of a pair exchanged on the way into the store"),
        ("odd_read_slice", "par2", "connection", OUT, "out_re1 <= norm(rd[2*WC-1:WC], e1);", "out_re1 <= norm(rd[WC-1:0], e1);", "the odd real part read from the odd imaginary slice"),
        ("tlast_early", "par2", "constant", OUT, "l1       <= issue && rlast;", "l1       <= issue && (idx == PW'(H - 2));", "tlast one beat early"),
        ("exp_not_aligned", "par2", "latency", OUT, "out_exp <= e1;", "out_exp <= sh_new;", "the exponent is two clocks ahead of the data (visible when frames follow each other with different levels)"),
        ("hold_missing", "par2", "connection", OUT, "en      = !(ov && !out_ready);", "en      = 1'b1;", "the read-out does not stall: beats are lost while the sink is not ready"),
        ("rd_not_held", "par2", "connection", OUT, "if (en) rd <= mem[", "rd <= mem[", "the memory output register is not held while the output is stalled"),
        ("exp_reg_not_held", "par2", "connection", OUT, "if (en) e1 <= sh_new;", "e1 <= sh_new;", "the exponent pipeline register is not held while the output is stalled"),
    ],
}
EQ_168: dict[str, list[str]] = {
    "fft_mdc2_axis": ["`win <= s_last` as `win <= 1'b1` in fft_mdc2_axis_ctl (window_flag_always): the window flag is read only in the clock after a transfer; inside a frame no clock passes without a transfer, so the flag set by a non-last beat is cleared by the next transfer before it is read. Run: it survives all six benches",
                      "`full[rb] <= 1'b0` as `full[wb] <= 1'b0` in fft_bfp_out_pair (full_clear_other): the read bank's flag stays set, but the reader only arrives at a bank with a stale flag when the previous read ended with the write pointer on that bank (no finished frame beyond it), and that same read clears the flag of the write bank. A stale flag can only be seen by the reader if the bank holds no finished frame, and then it was just cleared. Run: it survives all benches including `stress` (80 frames at NB 2 to 4, LOGN 4 and 5, random idles and random stalls) and `drain`; not proved"],
}
