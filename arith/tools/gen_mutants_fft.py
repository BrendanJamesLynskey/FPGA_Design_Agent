#!/usr/bin/env python3
"""Write verif/mutants.yaml of the frequency-domain functions (arith brief 148) from the lists below, checking that every `old` text occurs exactly once in the file it names.

    python3 -m arith.tools.gen_mutants_fft"""
from __future__ import annotations

import sys

import yaml

from arith.tools import arith_common as ac

# (name, variant, class, file or None, old, new, why)
M: dict[str, list[tuple]] = {
    "fft_cmul": [
        ("m4_im_minus", "m4", "operator", None, "sum_i = WP'(s_ri) + WP'(s_ir);", "sum_i = WP'(s_ri) - WP'(s_ir);", "the imaginary part subtracts its cross terms"),
        ("m4_re_plus", "m4", "operator", None, "sum_r = WP'(s_rr) - WP'(s_ii);", "sum_r = WP'(s_rr) + WP'(s_ii);", "the real part adds ai*bi instead of subtracting it"),
        ("m4_cross", "m4", "connection", None, "m_ri = xa * yb;", "m_ri = xa * ya;", "a cross product uses the wrong operand"),
        ("m4_ii", "m4", "connection", None, "m_ii = xb * yb;", "m_ii = xb * ya;", "the ai*bi product uses br"),
        ("m4_operand_rank", "m4", "latency", None, "xa = (STAGES >= 2) ? ar2 : ar1;", "xa = ar1;", "one operand skips its rank, so it is a clock early"),
        ("m4_product_rank", "m4", "latency", None, "s_rr = (STAGES >= 3) ? q_rr : m_rr;", "s_rr = m_rr;", "one product skips its rank"),
        ("m4_output_rank", "m4", "latency", None, "pr = (STAGES >= 1) ? reg_r : sum_r;", "pr = sum_r;", "the real output is not registered"),
        ("m3_re_plus", "m3", "operator", None, ") - ((STAGES >= 3) ? WP'(q2)", ") + ((STAGES >= 3) ? WP'(q2)", "the real part adds the second product"),
        ("m3_pre_dif", "m3", "operator", None, "b_dif = (WB + 1)'(sbi) - (WB + 1)'(sbr);", "b_dif = (WB + 1)'(sbi) + (WB + 1)'(sbr);", "the difference pre-adder adds"),
        ("m3_pre_sum", "m3", "operator", None, "a_sum = (WA + 1)'(sar) + (WA + 1)'(sai);", "a_sum = (WA + 1)'(sar) - (WA + 1)'(sai);", "the operand pre-adder subtracts"),
        ("m3_k3", "m3", "connection", None, "k3 = xr * yd;", "k3 = xi * yd;", "the third product uses ai"),
        ("m3_zero_ext", "m3", "width", None, "a_sum = (WA + 1)'(sar) + (WA + 1)'(sai);", "a_sum = (WA + 1)'(ar) + (WA + 1)'(sai);", "ar is zero-extended instead of sign-extended in the pre-adder"),
        ("m3_operand_rank", "m3", "latency", None, "xs = (STAGES >= 2) ? a_sum2 : a_sum;", "xs = a_sum;", "the pre-added operand skips its rank"),
        ("m3_k1", "m3", "connection", None, "k1 = xs * yr;", "k1 = xs * yd;", "the shared product uses the difference"),
    ],
    "fft_twiddle": [
        ("q1_cos_sign", "quarter", "constant", None, "2'd1:    begin cos_v = -sr; sin_v = cr;  end", "2'd1:    begin cos_v = sr;  sin_v = cr;  end", "second quadrant cosine has the wrong sign"),
        ("q2_sin_sign", "quarter", "constant", None, "2'd2:    begin cos_v = -cr; sin_v = -sr; end", "2'd2:    begin cos_v = -cr; sin_v = sr;  end", "third quadrant sine has the wrong sign"),
        ("q3_swap", "quarter", "constant", None, "default: begin cos_v = sr;  sin_v = -cr; end", "default: begin cos_v = sr;  sin_v = cr;  end", "fourth quadrant sine has the wrong sign"),
        ("sign_of_wi", "quarter", "operator", None, "nsin = -sin_v;", "nsin = sin_v;", "wi is +sin instead of -sin"),
        ("truncate", "quarter", "operator", None, "(32'(c0) + (32'd1 << (SH - 1)))", "(32'(c0))", "the cosine is truncated instead of rounded half up"),
        ("mirror", "quarter", "constant", None, "a1  = 11'd1024 - {1'b0, idx[9:0]};", "a1  = 11'd1023 - {1'b0, idx[9:0]};", "the mirrored table index is off by one"),
        ("index_scale", "quarter", "operator", None, "idx = 12'(m) << (12 - LOGC);", "idx = 12'(m) >> (12 - LOGC);", "the index is not scaled up to the master circle"),
        ("quadrant_delay", "quarter", "connection", None, "q_d <= q;", "q_d <= q_d;", "the quadrant is not delayed with the ROM read"),
        ("output_rank", "quarter", "latency", None, "wr = (STAGES >= 2) ? wr_q : cos_v;", "wr = cos_v;", "the cosine output skips its register"),
        ("rom_value", "quarter", "constant", "../fft_common/fft_cos_rom.sv", "11'd512: rom = 31'h2d413ccd;", "11'd512: rom = 31'h2d413cdd;", "one table entry (cos 45 degrees) is 16 counts off (a 28-bit twiddle sees it)"),
    ],
    "fft_reorder": [
        ("read_bank", "pingpong", "connection", None, "rd_bank <= wb;", "rd_bank <= ~wb;", "the bank just written is not the one read"),
        ("bank_toggle", "pingpong", "connection", None, "wb      <= ~wb;", "wb      <= wb;", "the write bank never toggles"),
        ("read_end", "pingpong", "constant", None, "if (rc == LOGN'(N - 1)) rd_on <= 1'b0;", "if (rc == LOGN'(N - 2)) rd_on <= 1'b0;", "the read stops one word early"),
        ("sof_pos", "pingpong", "constant", None, "s1 <= rd_on && (rc == '0);", "s1 <= rd_on && (rc == LOGN'(1));", "out_sof marks the second word"),
        ("bitrev_identity", "pingpong", "operator", "../fft_common/fft_bitrev.sv", "y[i] = a[LOGN-1-i];", "y[i] = a[i];", "no reversal"),
        ("bank_select", "pingpong", "connection", None, "b1 <= rd_bank;", "b1 <= wb;", "the output select follows the write bank"),
        ("out_mux", "pingpong", "connection", None, "out_d     = b1 ? rd1 : rd0;", "out_d     = b1 ? rd0 : rd1;", "the banks are swapped at the output"),
        ("write_bank", "pingpong", "connection", None, "if (wb) mem1[wpos] <= in_d;", "if (wb) mem0[wpos] <= in_d;", "both banks are written to bank 0"),
        ("bitrev_off", "pingpong", "operator", "../fft_common/fft_bitrev.sv", "for (int i = 0; i < LOGN; i++) y[i] = a[LOGN-1-i];", "for (int i = 0; i < LOGN - 1; i++) y[i] = a[LOGN-1-i];", "the top bit of the address is dropped (left X)"),
    ],
    "fft_window": [
        ("round_half", "dsp", "constant", None, "sr = (RND != 0) ? tr + (WD + WW + 1)'(1 << (WW - 1)) : tr;", "sr = (RND != 0) ? tr + (WD + WW + 1)'(1 << (WW - 2)) : tr;", "the rounding constant is a quarter instead of a half"),
        ("coef_sign", "dsp", "width", None, "ws = {1'b0, wu};", "ws = {wu[WW-1], wu};", "the coefficient is read as signed"),
        ("imag_uses_real", "dsp", "connection", None, "pi = ai * ws;", "pi = ar * ws;", "the imaginary part multiplies the real part"),
        ("coef_rank", "dsp", "latency", None, "wu = (STAGES >= 2) ? w2 : w;", "wu = w;", "the coefficient skips its operand rank"),
        ("output_rank", "dsp", "latency", None, "yr = (STAGES >= 1) ? yr_q : rr;", "yr = rr;", "the real output skips its register"),
        ("product_rank", "dsp", "latency", None, "tr = (STAGES >= 3) ? qr : pr;", "tr = pr;", "the real product skips its register"),
        ("rnd_inverted", "dsp", "operator", None, "sr = (RND != 0) ? tr +", "sr = (RND == 0) ? tr +", "rounding and truncation are exchanged"),
    ],
}
FFT_COMMON = [
    ("stage_mj", "sdf", "operator", "../fft_common/fft_sdf_stage.sv", "mj     = (TYP == 1) && second && c[(LD + 1 < LOGN) ? LD + 1 : LD];", "mj     = (TYP == 1) && second && !c[(LD + 1 < LOGN) ? LD + 1 : LD];", "the -j is applied to the wrong half"),
    ("stage_dif", "sdf", "operator", "../fft_common/fft_sdf_stage.sv", "dr = ar - br;", "dr = ar + br;", "the real difference adds"),
    ("stage_round", "sdf", "constant", "../fft_common/fft_sdf_stage.sv", "tsr = (SCALE != 0) ? ((sr + (WO + 2)'(RND)) >>> 1) : sr;", "tsr = (SCALE != 0) ? (sr >>> 1) : sr;", "the scaled sum is floored although RND asks for rounding"),
    ("stage_minus_j", "sdf", "operator", "../fft_common/fft_sdf_stage.sv", "bi = mj ? -(WO + 2)'(sxr) : (WO + 2)'(sxi);", "bi = mj ? (WO + 2)'(sxr) : (WO + 2)'(sxi);", "the -j has the sign of +j"),
    ("stage_store", "sdf", "connection", "../fft_common/fft_sdf_stage.sv", "in_r = second ? WO'(tdr) : WO'(sxr);", "in_r = second ? WO'(tsr) : WO'(sxr);", "the sum is fed back instead of the difference"),
    ("stage_pos", "sdf", "operator", "../fft_common/fft_sdf_stage.sv", "pos <= c - LOGN'(D);", "pos <= c + LOGN'(D);", "the position of the output word is wrong"),
    ("stage_half", "sdf", "operator", "../fft_common/fft_sdf_stage.sv", "second = c[LD];", "second = ~c[LD];", "the halves are exchanged"),
    ("stage_sof", "sdf", "connection", "../fft_common/fft_sdf_stage.sv", "c      = sof ? '0 : cnt;", "c      = cnt;", "the stage counter is never restarted"),
    ("tw_k", "sdf", "connection", "../fft_common/fft_sdf_twmul.sv", "k  = {g[0], g[1]};", "k  = g;", "the twiddle multiple is not the bit-reversed quarter"),
    ("tw_e2", "sdf", "operator", "../fft_common/fft_sdf_twmul.sv", "2'd2:    e = LM'(i) << 1;", "2'd2:    e = LM'(i);", "twice the index is not doubled"),
    ("tw_e3", "sdf", "operator", "../fft_common/fft_sdf_twmul.sv", "default: e = LM'(i) + (LM'(i) << 1);", "default: e = LM'(i) << 1;", "three times the index is doubled only"),
    ("tw_round", "sdf", "constant", "../fft_common/fft_sdf_twmul.sv", "rr = (RND != 0) ? (sr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : sr >>> (TW - 2);", "rr = (RND != 0) ? (sr + (WP)'(1 << (TW - 4))) >>> (TW - 2) : sr >>> (TW - 2);", "the product's rounding constant is a quarter"),
    ("tw_swap", "sdf", "connection", "../fft_common/fft_sdf_twmul.sv", "fft_cmul_m4 #(.WA(W), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES]), .ai(di[TWSTAGES]), .br(wr), .bi(wi), .pr(pr), .pi(pi));",
     "fft_cmul_m4 #(.WA(W), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES]), .ai(di[TWSTAGES]), .br(wi), .bi(wr), .pr(pr), .pi(pi));", "the twiddle's parts are exchanged"),
    ("sdf_latency_tap", "sdf", "constant", None, "if ((k % 2 == 1) && (k <= LOGN - 2)) a += LMUL;", "if ((k % 2 == 1) && (k <= LOGN - 2)) a += LMUL - 1;", "the stage markers are one clock early after a multiplier"),
    ("sdf_in_swap", "sdf", "connection", None, "x0r = inv_eff ? in_im : in_re;", "x0r = inv_eff ? in_re : in_re;", "the inverse does not swap at the input"),
    ("sdf_out_swap", "sdf", "connection", None, "br_r = inv_o ? bus_i[LOGN] : bus_r[LOGN];", "br_r = bus_r[LOGN];", "the inverse does not swap at the output"),
    ("sdf_tap", "sdf", "constant", None, "assign sof_s = sofc[lat_to(s)-1];", "assign sof_s = sofc[lat_to(s)];", "the stage marker is a clock late"),
    ("sdf_frame_end", "sdf", "constant", None, "if (sof_o) rem <= LOGN'(N - 1);", "if (sof_o) rem <= LOGN'(N - 2);", "out_valid ends a word early"),
    ("sdf_inv_hold", "sdf", "connection", None, "inv_eff = in_sof ? in_inverse : inv_q;", "inv_eff = in_inverse;", "the direction is read in every clock, not held from in_sof"),
    ("sdf_inv_tap", "sdf", "connection", None, "invc <= {invc[LTOT-2:0], in_inverse};", "invc <= {invc[LTOT-2:0], 1'b0};", "the direction flag never reaches the output swap"),
    ("sdf_wire_twiddle_sign", "sdf", "operator", "../fft_twiddle/rtl/fft_twiddle_quarter.sv", "2'd1:    begin cos_v = -sr; sin_v = cr;  end", "2'd1:    begin cos_v = sr;  sin_v = cr;  end", "second quadrant cosine has the wrong sign (seen through the FFT)"),
    ("sdf_wire_cmul_sign", "sdf", "operator", "../fft_cmul/rtl/fft_cmul_m4.sv", "sum_r = WP'(s_rr) - WP'(s_ii);", "sum_r = WP'(s_rr) + WP'(s_ii);", "the complex product's real part adds (seen through the FFT)"),
    ("sdf_reorder_bank", "sdf", "connection", "../fft_reorder/rtl/fft_reorder_pingpong.sv", "rd_bank <= wb;", "rd_bank <= ~wb;", "the reorder buffer reads the wrong bank (seen through the FFT, natural order)"),
]
BURST = [
    ("b_tm", "burst", "operator", None, "tm    = (j & mask) << st;", "tm    = (j & mask) << (st + 4'd1);", "the twiddle index is scaled for the wrong stage"),
    ("b_parity", "burst", "operator", None, "pa    = ^a;", "pa    = ^b;", "the bank of a is taken from b's parity"),
    ("b_hl", "burst", "operator", None, "hl    = 4'(LOGN - 1) - st;", "hl    = 4'(LOGN - 2) - st;", "the butterfly span is half"),
    ("b_round", "burst", "constant", None, "ts_r = WM'((SCALE != 0) ? ((s_r + (WM + 1)'(RND)) >>> 1) : s_r);", "ts_r = WM'((SCALE != 0) ? (s_r >>> 1) : s_r);", "the scaled sum is floored although RND asks for rounding"),
    ("b_dif", "burst", "operator", None, "d_r = (WM + 1)'(a_r) - (WM + 1)'(b_r);", "d_r = (WM + 1)'(a_r) + (WM + 1)'(b_r);", "the real difference adds"),
    ("b_wb", "burst", "connection", None, "wd0 = ld_we ? ld_d : (pa_p[LP] ? pw : sw);", "wd0 = ld_we ? ld_d : (pa_p[LP] ? sw : pw);", "bank 0 gets the wrong result"),
    ("b_drain", "burst", "constant", None, "if (cyc == CW'(N / 2 + LP - 1)) begin", "if (cyc == CW'(N / 2 - 1)) begin", "no pipeline drain between stages: a stage reads words not yet written"),
    ("b_unld", "burst", "connection", None, "ra0 = (ORDER == 0) ? ua[LOGN-1:1] : oc[LOGN-1:1];", "ra0 = (ORDER == 0) ? oc[LOGN-1:1] : ua[LOGN-1:1];", "the read order is exchanged"),
    ("b_out_swap", "burst", "connection", None, "out_re    = inv_f ? od[WM-1:0] : od[2*WM-1:WM];", "out_re    = od[2*WM-1:WM];", "the inverse does not swap at the output"),
    ("b_ld_swap", "burst", "connection", None, "ld_d    = {WM'(ldr), WM'(ldi)};", "ld_d    = {WM'(ldi), WM'(ldr)};", "real and imaginary parts are stored exchanged"),
    ("b_inv_hold", "burst", "connection", None, "inv_eff = (state == S_IDLE) ? in_inverse : inv_f;", "inv_eff = in_inverse;", "the direction is read in every clock, not held from in_sof"),
    ("b_tw_align", "burst", "latency", None, "wr2 = (TWSTAGES == 1) ? wr1 : wr0;", "wr2 = wr0;", "the twiddle is a clock early"),
    ("b_sum_path", "burst", "connection", None, "sd_r[0] <= ts_r;", "sd_r[0] <= td_r;", "the difference is written back where the sum belongs"),
    ("b_ready", "burst", "operator", None, "assign in_ready = (state == S_IDLE) && !ov;", "assign in_ready = 1'b1;", "in_ready never falls, so a frame can start while busy"),
    ("b_adv", "burst", "operator", None, "assign adv      = !ov || out_ready;", "assign adv      = 1'b1;", "the unload ignores out_ready (words are lost when the sink stalls)"),
    ("b_hold", "burst", "operator", None, "if (!(ov && !out_ready)) begin               // held while an output word waits for out_ready", "if (1'b1) begin", "the read registers are not held while the sink stalls (the data changes)"),
    ("b_load_end", "burst", "constant", None, "if (lc == LOGN'(N - 1)) begin\n                            state <= S_COMP;", "if (lc == LOGN'(N - 2)) begin\n                            state <= S_COMP;", "the load ends a word early"),
]
M["fft_axis"] = [
    ("a_sof", "sdf", "connection", None, "in_sof        = at_start;", "in_sof        = 1'b1;", "every beat is a start of frame"),
    ("a_start", "sdf", "operator", None, "else if (in_valid) at_start <= s_axis_tlast;", "else if (in_valid) at_start <= !s_axis_tlast;", "the start flag follows the wrong polarity of tlast"),
    ("a_tuser", "sdf", "connection", None, ".in_inverse(s_axis_tuser)", ".in_inverse(1'b0)", "tuser never reaches the core"),
    ("a_pack", "sdf", "connection", None, "m_axis_tdata  = {out_im, out_re};", "m_axis_tdata  = {out_re, out_im};", "real and imaginary parts exchanged on the output"),
    ("a_tlast", "sdf", "constant", None, "m_axis_tlast  = out_valid && (cnt == LOGN'(N - 1));", "m_axis_tlast  = out_valid && (cnt == LOGN'(N - 2));", "tlast one beat early"),
    ("a_in_re", "sdf", "connection", None, ".in_re(s_axis_tdata[W-1:0]), .in_im(s_axis_tdata[2*W-1:W])", ".in_re(s_axis_tdata[2*W-1:W]), .in_im(s_axis_tdata[W-1:0])", "real and imaginary parts exchanged on the input"),
    ("a_ocnt", "sdf", "connection", None, "else if (out_valid && 1'b1) ocnt <= cnt + 1'b1;", "else if (out_valid && 1'b0) ocnt <= cnt + 1'b1;", "the output beat counter never advances"),
    ("b_ready", "burst", "connection", None, "s_axis_tready = core_ready || !at_start;", "s_axis_tready = core_ready;", "tready low during the load: the frame cannot be loaded"),
    ("b_valid_ready", "burst", "operator", None, "m_axis_tvalid = out_valid;", "m_axis_tvalid = out_valid && m_axis_tready;", "tvalid depends on tready (an AXI4-Stream rule violation: it drops while stalled)"),
    ("b_ocnt", "burst", "connection", None, "else if (out_valid && m_axis_tready) ocnt <= cnt + 1'b1;", "else if (out_valid) ocnt <= cnt + 1'b1;", "the output beat counter advances on stalled clocks (tlast in the wrong place under back-pressure)"),
    ("b_out_ready", "burst", "connection", None, ".out_ready(m_axis_tready)", ".out_ready(1'b1)", "the core never stalls: data changes while the sink is not ready"),
    ("b_tuser", "burst", "connection", None, ".in_inverse(s_axis_tuser)", ".in_inverse(1'b0)", "tuser never reaches the core"),
    ("b_in_valid", "burst", "operator", None, "in_valid      = s_axis_tvalid && s_axis_tready;", "in_valid      = s_axis_tvalid;", "beats are taken that were not accepted (tready low)"),
]
M["fft_real"] = [
    ("r_e_sign", "post", "operator", None, "ei  = WE'(ai) - WE'(bi);", "ei  = WE'(ai) + WE'(bi);", "E uses Z[N/2-k] instead of its conjugate (imaginary part)"),
    ("r_o_real", "post", "operator", None, "orr = WE'(ar) - WE'(br);", "orr = WE'(ar) + WE'(br);", "O adds the real parts"),
    ("r_o_imag", "post", "operator", None, "oi  = WE'(ai) + WE'(bi);", "oi  = WE'(ai) - WE'(bi);", "O subtracts the imaginary parts"),
    ("r_minus_j", "post", "operator", None, "ji  <= -WA'(sor);", "ji  <= WA'(sor);", "the quarter turn has the wrong sign"),
    ("r_shift", "post", "constant", None, "localparam int SH = 1 + SCALE;", "localparam int SH = 1;", "the scaled mode shifts once instead of twice"),
    ("r_mirror", "post", "operator", None, "rb = LH'(0) - k[LH-1:0];", "rb = LH'(H - 1) - k[LH-1:0];", "the mirrored index is N/2 - 1 - k"),
    ("r_bank", "post", "connection", None, "rbank <= wbank;", "rbank <= ~wbank;", "the bank being written is read"),
    ("r_wr_order", "post", "connection", None, "mem_b[{wbank, wa}] <= {zr, zi};", "mem_b[{wbank, wpos}] <= {zr, zi};", "the second memory copy stores Z in arrival order instead of at bit-reversed addresses"),
    ("r_twiddle_k", "post", "connection", None, "kk = k;", "kk = k + 1'b1;", "the twiddle index is k + 1"),
    ("r_core_width", "post", "width", None, "cre = (W + 1)'(se);", "cre = (W + 1)'(in_even);", "the even sample is zero-extended into the core (negative samples wrong)"),
    ("r_last", "post", "constant", None, "if (k == LOGN'(H)) rd_on <= 1'b0;", "if (k == LOGN'(H - 1)) rd_on <= 1'b0;", "the read-out stops one bin early"),
    ("r_align", "post", "latency", None, "wr2 = (TWSTAGES == 1) ? wr1 : wr0;", "wr2 = wr0;", "the twiddle is a clock early"),
    ("r_round_p", "post", "constant", None, "rr = (RND != 0) ? (spr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : spr >>> (TW - 2);", "rr = (RND != 0) ? (spr + (WP)'(1 << (TW - 4))) >>> (TW - 2) : spr >>> (TW - 2);", "the product's rounding constant is a quarter"),
]
M["fft"] = FFT_COMMON + BURST
# mutants argued equivalent and left out (named in the header of each mutants.yaml)
EQUIVALENT = {
    "fft_window": ["shift_logical: `sr >> WW` instead of `sr >>> WW` on the signed product: the bits above the kept WD bits are the only ones a logical shift changes, and they are cut off by the truncation to WD bits, so the output is the same"],
    "fft_reorder": ["wpos = wc (no restart at in_sof): the write counter wraps at N, so for the contiguous frames of exactly N words the protocol requires it equals the restarted counter; it differs only when a frame is cut short, which is outside the protocol and is documented in spec.md"],
    "fft": ["burst `b = a | h` replaced by `a + h`: bit h of a is zero by construction, so the two are the same",
            "burst `ua_par = ^oc` instead of `^ua` (ua is the bit reversal of oc): reversing the bits does not change how many are set, so the parities are equal"],
}
EXTRA = {"fft": ("sdf", "burst")}


def main() -> int:
    for fn, ms in M.items():
        spec = ac.load_spec(fn)
        d = ac.ARITH / fn
        names = set()
        for name, var, cls, file, old, new, why in ms:
            assert name not in names, name
            names.add(name)
            tf = d / (file or spec["variants"][var]["file"])
            n = tf.read_text().count(old)
            if n != 1:
                print(f"{fn}/{name}: `old` occurs {n} times in {tf.relative_to(ac.ROOT)}")
                return 1
        y = [{"name": n, "variant": v, "class": c, **({"file": f} if f else {}), "old": o, "new": nw, "why": w} for n, v, c, f, o, nw, w in ms]
        eq = "".join(f"# Left out as equivalent: {e}\n" for e in EQUIVALENT.get(fn, []))
        head = (f"# Mutation set for {fn} (arith brief 148; tools/run_mutants.py): each mutant replaces `old` (exactly once) by `new` in a copy of the file it names (the variant's own file, or `file`,\n"
                "# relative to this function's folder, for a mutant of a shared file). Generated by arith/tools/gen_mutants_fft.py: edit that list, not this file. Mutants left out as equivalent are listed in\n"
                "# the lines below.\n" + eq)
        (d / "verif" / "mutants.yaml").write_text(head + "mutants:\n" + "".join("- " + yaml.safe_dump(m, default_flow_style=True, width=1000).strip() + "\n" for m in y))
        print("wrote", fn, len(y))
    return 0


if __name__ == "__main__":
    sys.exit(main())
