`timescale 1ns / 1ps
// rig_copy.sv: one copy of one crossing variant, with its source, its checker and its record
// (reports/11_cdc_soak_rig_design.md section 2). VAR is a rig_pkg::V_* code, K the copy's index within its variant
// (which sets direction and placement class), G its global index.
//
// Naming, which the constraints (constr/rig_cdc.tcl) and the delay table (tcl/delay_table.tcl) rely on:
//   pbs_*   placed in the copy's source pblock      pbd_*   placed in its destination pblock
//   syn_s1  first flop of a correct 1-bit synchroniser (false path to it)
//   gsyn_*  first flops of a correct Gray bus (max_delay -datapath_only + bus_skew, per copy)
//   hsd_* / ramrd_*  multi-bit capture of data held stable by a handshake / a FIFO (max_delay -datapath_only)
//   mut_*   the endpoint of a mutant crossing (false path for timing, waived in report_cdc/report_methodology)
//   brg_*   reset bridge flops (false path to their asynchronous clear)

module rig_copy #(
    parameter int VAR = 0,
    parameter int K   = 0,
    parameter int G   = 0,
    parameter int WDB = 16                 // lock-up watchdog: 2^WDB destination cycles
) (
    input  logic clk_a, clk_b, clk_c, clk_f,
    input  logic por_a, por_b, por_c, por_f,     // power-on resets, each released in its own domain
    input  logic run_a, run_b, run_c, run_f,     // sources may run (each in its own domain)
    input  logic hold_a, hold_b, hold_c,         // quiesce seen (watchdogs off), destination domains
    input  logic frz_a, frz_b, frz_c,            // counters frozen
    input  logic sh_a, sh_b, sh_c,               // shift the record chain one bit
    input  logic sin,
    output logic sout,
    input  logic rq_s, rq_d, rq_any, rq_d2       // reset-storm requests: this copy's own raw clk_a registers
);
    import rig_pkg::*;
    localparam int SD  = sdom(VAR, K);
    localparam int DD  = ddom(VAR, K);
    localparam int CLS = cls_of(K);
    localparam logic [15:0] SEED = 16'((G * 40503 + 7919) % 65535 + 1);

    // (constants for the generate blocks below: Icarus 12 does not see package names inside generate scopes)
    localparam int  C1_STAGES = VAR == V_C1 ? 2 : 3;
    localparam int  C3_STAGES = VAR == V_C3A ? 2 : 4;
    localparam bit  LVL_CHK   = VAR != V_C4 && VAR != V_C5 && VAR != V_M5;
    localparam int  M6_LUTS   = VAR == V_M6B ? 4 : 24;     // M6c: 24 route-through LUTs (brief 11c; was 8)
    localparam bit  C13_SYNC  = VAR == V_C13;              // C13 resets synchronously (brief 11c)
    localparam bit  M6_FAST   = VAR == V_M6B || VAR == V_M6C;
    wire sclk  = SD == D_A ? clk_a : SD == D_B ? clk_b : SD == D_C ? clk_c : clk_f;
    wire dclk  = DD == D_A ? clk_a : DD == D_B ? clk_b : clk_c;
    wire s_por = SD == D_A ? por_a : SD == D_B ? por_b : SD == D_C ? por_c : por_f;
    wire d_por = DD == D_A ? por_a : DD == D_B ? por_b : por_c;
    wire s_run = SD == D_A ? run_a : SD == D_B ? run_b : SD == D_C ? run_c : run_f;
    wire d_hld = DD == D_A ? hold_a : DD == D_B ? hold_b : hold_c;
    wire d_frz = DD == D_A ? frz_a : DD == D_B ? frz_b : frz_c;
    wire d_sh  = DD == D_A ? sh_a : DD == D_B ? sh_b : sh_c;

    logic e_err, e_ev, e_lock, e_relock;
    rec_cnt u_rec (.clk(dclk), .frz(d_frz), .sh(d_sh), .sin(sin), .sout(sout),
                   .e_err(e_err), .e_ev(e_ev), .e_lock(e_lock), .e_relock(e_relock));

    // random enables in the destination (readers)
    logic [15:0] d_lf;
    lfsr16 #(.SEED(SEED ^ 16'h5A5A | 16'h1)) u_dlf (.clk(dclk), .rst(1'b0), .en(1'b1), .q(d_lf));

    // ------------------------------------------------------------------ single-bit crossings and pulses
    if (grp_of(VAR) == 0) begin : g_v
        logic tog, pls;
        logic [7:0] cnt, refc;
        src_ev #(.SEED(SEED)) pbs_src (.clk(sclk), .rst(s_por), .run(s_run), .tog(tog), .pls(pls), .cnt(cnt));
        xpm_cdc_gray #(.DEST_SYNC_FF(3), .WIDTH(8), .REG_OUTPUT(1))
            u_ref (.src_clk(sclk), .src_in_bin(cnt), .dest_clk(dclk), .dest_out_bin(refc));
        logic lvl, ev;                       // the crossing's output: a level (lvl) or a pulse (ev)
        logic pbd_lp = 1'b0;
        always_ff @(posedge dclk) pbd_lp <= lvl;
        if (VAR == V_C1 || VAR == V_C2) begin : g_hand
            sync_n #(.STAGES(C1_STAGES)) pbd_x (.clk(dclk), .d(tog), .q(lvl));
            assign ev = lvl != pbd_lp;
        end else if (VAR == V_C3A || VAR == V_C3B) begin : g_xpm
            xpm_cdc_single #(.DEST_SYNC_FF(C3_STAGES), .SRC_INPUT_REG(0))
                u_x (.src_clk(sclk), .src_in(tog), .dest_clk(dclk), .dest_out(lvl));
            assign ev = lvl != pbd_lp;
        end else if (VAR == V_M1) begin : g_m1
            logic m;                         // no ASYNC_REG; first flop in the source pblock, second in the destination
            cff #(.INJ(1'b1)) pbs_mut_m1 (.clk(dclk), .arst(1'b0), .d(tog), .q(m));
            cff               pbd_m1b    (.clk(dclk), .arst(1'b0), .d(m),   .q(lvl));
            assign ev = lvl != pbd_lp;
        end else if (VAR == V_M1B) begin : g_m1b
            cff #(.INJ(1'b1)) pbd_mut_m1b (.clk(dclk), .arst(1'b0), .d(tog), .q(lvl));
            assign ev = lvl != pbd_lp;
        end else if (VAR == V_C4) begin : g_c4
            logic pbs_tg = 1'b0;
            always_ff @(posedge sclk) if (pls) pbs_tg <= ~pbs_tg;
            sync_n #(.STAGES(2)) pbd_x (.clk(dclk), .d(pbs_tg), .q(lvl));
            assign ev = lvl != pbd_lp;
        end else if (VAR == V_C5) begin : g_c5
            xpm_cdc_pulse #(.DEST_SYNC_FF(3), .REG_OUTPUT(1), .RST_USED(0))
                u_x (.src_clk(sclk), .src_pulse(pls), .dest_clk(dclk), .src_rst(1'b0), .dest_rst(1'b0),
                     .dest_pulse(ev));
            assign lvl = 1'b0;
        end else if (VAR == V_M5) begin : g_m5
            logic m;                         // a one-cycle pulse into a level synchroniser, no stretch
            cff #(.ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m5 (.clk(dclk), .arst(1'b0), .d(pls), .q(m));
            cff #(.ASYNC(1'b1))             pbd_m5b    (.clk(dclk), .arst(1'b0), .d(m),   .q(lvl));
            assign ev = lvl && !pbd_lp;
        end
        if (VAR == V_M2) begin : g_m2
            logic m0, m1, q0, q1;            // one asynchronous bit into two flops, compared
            // DONT_TOUCH on the instances: synthesis otherwise "declones" the two identical capture flops into one
            (* DONT_TOUCH = "TRUE" *) cff #(.INJ(1'b1)) pbs_mut_m2a (.clk(dclk), .arst(1'b0), .d(tog), .q(m0));
            (* DONT_TOUCH = "TRUE" *) cff #(.INJ(1'b1)) pbd_mut_m2b (.clk(dclk), .arst(1'b0), .d(tog), .q(m1));
            (* DONT_TOUCH = "TRUE" *) cff pbd_m2c (.clk(dclk), .arst(1'b0), .d(m0), .q(q0));
            (* DONT_TOUCH = "TRUE" *) cff pbd_m2d (.clk(dclk), .arst(1'b0), .d(m1), .q(q1));
            chk_pair u_chk (.clk(dclk), .a(q0), .b(q1), .e_err(e_err), .e_ev(e_ev));
            assign lvl = 1'b0;
            assign ev = 1'b0;
        end else if (VAR == V_M7) begin : g_m7
            (* DONT_TOUCH = "TRUE" *) logic pbs_m7f0 = 1'b0;
            (* DONT_TOUCH = "TRUE" *) logic pbs_m7f1 = 1'b0;
            always_ff @(posedge sclk) if (pls) begin pbs_m7f0 <= ~pbs_m7f0; pbs_m7f1 <= ~pbs_m7f1; end
            logic m0, m1, q0, q1;            // two flags set on one edge, synchronised separately, then combined
            cff #(.ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m7a (.clk(dclk), .arst(1'b0), .d(pbs_m7f0), .q(m0));
            cff #(.ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m7b (.clk(dclk), .arst(1'b0), .d(pbs_m7f1), .q(m1));
            cff #(.ASYNC(1'b1)) pbd_m7c (.clk(dclk), .arst(1'b0), .d(m0), .q(q0));
            cff #(.ASYNC(1'b1)) pbd_m7d (.clk(dclk), .arst(1'b0), .d(m1), .q(q1));
            chk_pair u_chk (.clk(dclk), .a(q0), .b(q1), .e_err(e_err), .e_ev(e_ev));
            assign lvl = 1'b0;
            assign ev = 1'b0;
        end else if (VAR == V_M4) begin : g_m4
            // two coincident toggles, XORed before the synchroniser: the XOR should never change
            (* DONT_TOUCH = "TRUE" *) logic pbs_m4t0 = 1'b0;
            (* DONT_TOUCH = "TRUE" *) logic pbd_m4t1 = 1'b0;   // clocked by the source, placed with the destination
            always_ff @(posedge sclk) if (pls) begin pbs_m4t0 <= ~pbs_m4t0; pbd_m4t1 <= ~pbd_m4t1; end
            logic x, m, xs, xp = 1'b0;
            logic [7:0] rp = '0;
`ifdef CDC_SIM
            // the route delta between the two inputs, modelled as a transport delay (far 2 ns, boundary 1 ns, near 20 ps)
            logic t1d;
            assign #(CLS == 0 ? 2.0 : CLS == 2 ? 1.0 : 0.02) t1d = pbd_m4t1;
            assign x = pbs_m4t0 ^ t1d;
`else
            (* DONT_TOUCH = "TRUE" *) LUT2 #(.INIT(4'h6)) u_xor (.I0(pbs_m4t0), .I1(pbd_m4t1), .O(x));
`endif
            cff #(.ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m4 (.clk(dclk), .arst(1'b0), .d(x), .q(m));
            cff #(.ASYNC(1'b1))             pbd_m4b    (.clk(dclk), .arst(1'b0), .d(m), .q(xs));
            always_ff @(posedge dclk) begin
                xp <= xs; rp <= refc;
                e_err <= xs != xp;
                e_ev  <= refc != rp;
            end
            assign lvl = 1'b0;
            assign ev = 1'b0;
        end else begin : g_ev
            chk_events u_chk (.clk(dclk), .ev(ev), .ref_cnt(refc), .lvl_chk(LVL_CHK),
                              .e_err(e_err), .e_ev(e_ev));
        end
        assign e_lock = 1'b0;
        assign e_relock = 1'b0;

    // ------------------------------------------------------------------ Gray and binary counters
    end else if (grp_of(VAR) == 1) begin : g_v
        localparam int NINC = M6_FAST ? 1 : 4;     // source steps every NINC cycles
        logic [11:0] pbs_bin = '0;
        logic [1:0]  pbs_div = '0;
        always_ff @(posedge sclk)
            if (s_por) begin pbs_bin <= '0; pbs_div <= '0; end
            else if (s_run) begin
                pbs_div <= pbs_div + 1'b1;
                if (NINC == 1 || pbs_div == 2'(NINC - 1)) pbs_bin <= pbs_bin + 1'b1;
            end
        logic [11:0] v, raw;
        if (VAR == V_C6) begin : g_c6
            logic [11:0] pbs_gray = '0, g1;
            always_ff @(posedge sclk) pbs_gray <= bin2gray12(pbs_bin);
            cff #(.W(12), .ASYNC(1'b1), .INJ(1'b1)) pbd_gsyn_g (.clk(dclk), .arst(1'b0), .d(pbs_gray), .q(g1));
            cff #(.W(12), .ASYNC(1'b1))             pbd_gs2_g  (.clk(dclk), .arst(1'b0), .d(g1), .q(raw));
            assign v = gray2bin12(raw);
            chk_count #(.MAXSTEP(2), .RAWCHK(1)) u_chk (.clk(dclk), .v(v), .raw(raw), .e_err(e_err), .e_ev(e_ev));
        end else if (VAR == V_C7) begin : g_c7
            xpm_cdc_gray #(.DEST_SYNC_FF(3), .WIDTH(12), .REG_OUTPUT(1))
                u_x (.src_clk(sclk), .src_in_bin(pbs_bin), .dest_clk(dclk), .dest_out_bin(v));
            assign raw = '0;
            chk_count #(.MAXSTEP(2)) u_chk (.clk(dclk), .v(v), .raw(raw), .e_err(e_err), .e_ev(e_ev));
        end else if (VAR == V_M3) begin : g_m3
            logic [11:0] b1;                 // binary counter crossed bit by bit
            cff #(.W(12), .ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m3 (.clk(dclk), .arst(1'b0), .d(pbs_bin), .q(b1));
            cff #(.W(12), .ASYNC(1'b1))             pbd_m3b    (.clk(dclk), .arst(1'b0), .d(b1), .q(v));
            assign raw = '0;
            chk_count #(.MAXSTEP(2)) u_chk (.clk(dclk), .v(v), .raw(raw), .e_err(e_err), .e_ev(e_ev));
        end else if (VAR == V_M6A) begin : g_m6a
            // Gray with no bus_skew/max_delay; even bits launched from the source pblock, odd bits from the destination
            logic [5:0] pbs_m6ge = '0, pbd_m6go = '0;
            wire  [11:0] gr;
            logic [11:0] g1;
            always_ff @(posedge sclk) begin
                for (int i = 0; i < 6; i++) begin
                    pbs_m6ge[i] <= bin2gray12(pbs_bin) >> (2 * i);
                    pbd_m6go[i] <= bin2gray12(pbs_bin) >> (2 * i + 1);
                end
            end
            for (genvar i = 0; i < 6; i++) begin : il
                assign gr[2*i] = pbs_m6ge[i];
                assign gr[2*i+1] = pbd_m6go[i];
            end
            cff #(.W(12), .ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m6 (.clk(dclk), .arst(1'b0), .d(gr), .q(g1));
            cff #(.W(12), .ASYNC(1'b1))             pbd_m6b    (.clk(dclk), .arst(1'b0), .d(g1), .q(raw));
            assign v = gray2bin12(raw);
            chk_count #(.MAXSTEP(2), .RAWCHK(1)) u_chk (.clk(dclk), .v(v), .raw(raw), .e_err(e_err), .e_ev(e_ev));
        end else begin : g_m6bc
            // 250 MHz source; odd bits padded with 4 (M6b) or 8 (M6c) route-through LUTs, no bus_skew
            logic [11:0] pbs_gray = '0, g1;
            wire  [11:0] gd;
            always_ff @(posedge sclk) pbs_gray <= bin2gray12(pbs_bin);
            for (genvar i = 0; i < 12; i++) begin : bit_i
                if (i % 2 == 1) begin : pad
                    rt_delay #(.N(M6_LUTS)) u_rt (.a(pbs_gray[i]), .y(gd[i]));
                end else begin : nopad
                    assign gd[i] = pbs_gray[i];
                end
            end
            cff #(.W(12), .ASYNC(1'b1), .INJ(1'b1)) pbd_mut_m6 (.clk(dclk), .arst(1'b0), .d(gd), .q(g1));
            cff #(.W(12), .ASYNC(1'b1))             pbd_m6b    (.clk(dclk), .arst(1'b0), .d(g1), .q(raw));
            assign v = gray2bin12(raw);
            // reference (brief 11c): the same source register through a correct bank (rsyn_*: max_delay and a bus_skew
            // below one source period), captured on the same destination edges; a tear of two counts or more shows
            logic [11:0] r1, rr;
            cff #(.W(12), .ASYNC(1'b1), .INJ(1'b1)) pbd_rsyn_g (.clk(dclk), .arst(1'b0), .d(pbs_gray), .q(r1));
            cff #(.W(12), .ASYNC(1'b1))             pbd_rsyn_g2 (.clk(dclk), .arst(1'b0), .d(r1), .q(rr));
            // CFGMCLK may be as slow as 32 MHz: up to 8 source steps per destination sample
            chk_tear #(.MAXSTEP(10)) u_chk (.clk(dclk), .v(v), .vref(gray2bin12(rr)), .e_err(e_err), .e_ev(e_ev));
        end
        assign e_lock = 1'b0;
        assign e_relock = 1'b0;

    // ------------------------------------------------------------------ handshakes
    end else if (grp_of(VAR) == 2) begin : g_v
        logic valid;
        logic [15:0] w;
        logic arm = 1'b0;
        if (VAR == V_C8) begin : g_c8
            // 4-phase: req up with data, ack up, req down, ack down
            logic [15:0] pbs_data = SEED;
            logic pbs_req = 1'b0, pbs_busy = 1'b0, pbd_ack = 1'b0, pbd_v = 1'b0, req_d, ack_s;
            logic [15:0] pbd_hsd_w = '0;
            sync_n #(.STAGES(2)) pbs_ack_s (.clk(sclk), .d(pbd_ack), .q(ack_s));
            sync_n #(.STAGES(2)) pbd_req_s (.clk(dclk), .d(pbs_req), .q(req_d));
            always_ff @(posedge sclk)
                if (s_por) begin pbs_req <= 1'b0; pbs_busy <= 1'b0; pbs_data <= SEED; end
                else if (!pbs_busy) begin
                    if (s_run && !ack_s) begin pbs_data <= prbs16_next(pbs_data); pbs_req <= 1'b1; pbs_busy <= 1'b1; end
                end else if (pbs_req && ack_s) pbs_req <= 1'b0;
                else if (!pbs_req && !ack_s) pbs_busy <= 1'b0;
            always_ff @(posedge dclk) begin
                pbd_v <= 1'b0;
                if (req_d && !pbd_ack) begin pbd_hsd_w <= pbs_data; pbd_v <= 1'b1; pbd_ack <= 1'b1; end
                else if (!req_d) pbd_ack <= 1'b0;
            end
            assign valid = pbd_v;
            assign w = pbd_hsd_w;
        end else if (VAR == V_C9) begin : g_c9
            logic [15:0] pbs_data = SEED, dout;
            logic pbs_send = 1'b0, rcv, dreq, pbd_ack = 1'b0, pbd_v = 1'b0;
            logic [15:0] pbd_w = '0;
            xpm_cdc_handshake #(.DEST_EXT_HSK(1), .DEST_SYNC_FF(3), .SRC_SYNC_FF(3), .WIDTH(16))
                u_x (.src_clk(sclk), .src_in(pbs_data), .src_send(pbs_send), .src_rcv(rcv),
                     .dest_clk(dclk), .dest_out(dout), .dest_req(dreq), .dest_ack(pbd_ack));
            always_ff @(posedge sclk)
                if (s_por) begin pbs_send <= 1'b0; pbs_data <= SEED; end
                else if (!pbs_send && !rcv && s_run) begin pbs_data <= prbs16_next(pbs_data); pbs_send <= 1'b1; end
                else if (pbs_send && rcv) pbs_send <= 1'b0;
            always_ff @(posedge dclk) begin
                pbd_v <= 1'b0;
                if (dreq && !pbd_ack) begin pbd_w <= dout; pbd_v <= 1'b1; pbd_ack <= 1'b1; end
                else if (!dreq) pbd_ack <= 1'b0;
            end
            assign valid = pbd_v;
            assign w = pbd_w;
        end else begin : g_m11
            // 2-phase (toggle) handshake; the source side is reset by the storms, the destination side is not
            logic srst, srst_b, req_d, ack_s, rqs_d, rqs_p = 1'b0;
            logic [15:0] pbs_data = SEED;
            logic pbs_req = 1'b0, pbd_ack = 1'b0, pbd_v = 1'b0;
            logic [15:0] pbd_hsd_w = '0;
            rst_bridge pbs_rb (.clk(sclk), .arst_in(rq_s), .sync_in(s_por), .rst_out(srst));
            assign srst_b = srst;
            sync_n #(.STAGES(2)) pbs_ack_s (.clk(sclk), .d(pbd_ack), .q(ack_s));
            sync_n #(.STAGES(2)) pbd_req_s (.clk(dclk), .d(pbs_req), .q(req_d));
            always_ff @(posedge sclk or posedge srst)
                if (srst) begin pbs_req <= 1'b0; pbs_data <= SEED; end
                else if (s_run && ack_s == pbs_req) begin pbs_data <= prbs16_next(pbs_data); pbs_req <= ~pbs_req; end
            always_ff @(posedge dclk) begin
                pbd_v <= 1'b0;
                if (req_d != pbd_ack) begin pbd_hsd_w <= pbs_data; pbd_v <= 1'b1; pbd_ack <= req_d; end
            end
            sync_n #(.STAGES(2)) pbd_rq_s (.clk(dclk), .d(rq_s), .q(rqs_d));
            always_ff @(posedge dclk) begin rqs_p <= rqs_d; arm <= rqs_d && !rqs_p; end
            assign valid = pbd_v;
            assign w = pbd_hsd_w;
        end
        chk_words #(.WDB(WDB)) u_chk (.clk(dclk), .valid(valid), .w(w), .arm(arm), .hold(d_hld), .e_err(e_err),
                                      .e_ev(e_ev), .e_relock(e_relock), .e_lock(e_lock));

    // ------------------------------------------------------------------ FIFOs
    end else if (grp_of(VAR) == 3) begin : g_v
        logic valid, arm = 1'b0;
        logic [15:0] w;
        logic [15:0] s_lf;
        lfsr16 #(.SEED(SEED ^ 16'h3C3C | 16'h1)) u_slf (.clk(sclk), .rst(1'b0), .en(1'b1), .q(s_lf));
        if (VAR == V_C11) begin : g_c11
            logic brs, brs_b, pbs_rst = 1'b1, full, empty, wbusy, rbusy, pbd_v = 1'b0, rq, rqp = 1'b0;
            logic [15:0] pbs_data = SEED, dout;
            rst_bridge pbs_rb (.clk(sclk), .arst_in(rq_any), .sync_in(s_por), .rst_out(brs));
            assign brs_b = brs;
            always_ff @(posedge sclk) pbs_rst <= brs && (pbs_rst || !wbusy);
            wire we = s_run && !full && !wbusy && !pbs_rst && s_lf[0];
            always_ff @(posedge sclk)
                if (pbs_rst) pbs_data <= SEED;
                else if (we) pbs_data <= prbs16_next(pbs_data);
            wire re = !empty && !rbusy && d_lf[0];
            xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"), .FIFO_WRITE_DEPTH(512), .WRITE_DATA_WIDTH(16),
                             .READ_DATA_WIDTH(16), .READ_MODE("std"), .FIFO_READ_LATENCY(1), .CDC_SYNC_STAGES(2),
                             .USE_ADV_FEATURES("0000"), .DOUT_RESET_VALUE("0"))
                u_fifo (.sleep(1'b0), .rst(pbs_rst), .wr_clk(sclk), .wr_en(we), .din(prbs16_next(pbs_data)),
                        .full(full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(wbusy),
                        .almost_full(), .wr_ack(), .rd_clk(dclk), .rd_en(re), .dout(dout), .empty(empty),
                        .prog_empty(), .rd_data_count(), .underflow(), .rd_rst_busy(rbusy), .almost_empty(),
                        .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr());
            always_ff @(posedge dclk) pbd_v <= re;
            sync_n #(.STAGES(2)) pbd_rq_s (.clk(dclk), .d(rq_any), .q(rq));
            always_ff @(posedge dclk) begin rqp <= rq; arm <= rq && !rqp; end
            assign valid = pbd_v;
            assign w = dout;
        end else begin : g_hand
            logic wrst, rrst, full, empty, pbd_v = 1'b0, rq, rqe, rqp = 1'b0;
            logic [15:0] pbs_data = SEED, rdata, pbd_ramrd_w = '0;
            if (VAR == V_C10) begin : g_r
                assign wrst = s_por;
                assign rrst = d_por;
                assign rq = 1'b0;
                assign rqe = 1'b0;
            end else if (VAR == V_C13) begin : g_r
`ifdef CDC_C13_LEGACY
                // the version of the first board runs (kept for the simulation that reproduces its failure): both sides
                // cleared asynchronously through a bridge each, the checker re-armed from the raw bridge output
                rst_bridge pbs_rb (.clk(sclk), .arst_in(rq_any), .sync_in(s_por), .rst_out(wrst));
                rst_bridge pbd_rb (.clk(dclk), .arst_in(rq_any), .sync_in(d_por), .rst_out(rrst));
                // two flops sampling one asynchronous signal, each with its own resolution (metastability injection)
                logic rq_a, rq_p;
                cff #(.INJ(1'b1)) pbd_arm_a (.clk(dclk), .arst(1'b0), .d(rrst), .q(rq_a));
                cff #(.INJ(1'b1)) pbd_arm_p (.clk(dclk), .arst(1'b0), .d(rrst), .q(rq_p));
                assign rq  = rq_a;
                assign rqe = rq_p;
`else
                // Reader first, writer second, both synchronous (brief 11c). The request is synchronised into the reader's
                // clock (rs); the reader's reset flag rrst_r is a flop of its clock and resets its pointers synchronously;
                // the writer resets from that flag, synchronised into its clock. So the reader is always in reset before
                // the writer's reset can reach it through the pointers, the words it captured before are in sequence, and
                // the re-arm of the checker reads a flop of its own clock. (The first version cleared both sides
                // asynchronously from the request: it let the checker sample an asynchronous signal with two flops, and
                // the read address and qualifier change inside a cycle.) The request is held at least 50 clk_a cycles,
                // longer than both entries (3 + 3 cycles of the slower clock) plus the pointer synchronisers.
                logic rs, ws;
                logic pbd_rrst_r = 1'b1, pbs_wrst_r = 1'b1;
                sync_n #(.STAGES(2)) pbd_rq_s (.clk(dclk), .d(rq_any), .q(rs));
                always_ff @(posedge dclk) pbd_rrst_r <= rs | d_por;
                sync_n #(.STAGES(2)) pbs_rr_s (.clk(sclk), .d(pbd_rrst_r), .q(ws));
                always_ff @(posedge sclk) pbs_wrst_r <= ws | s_por;
                assign rrst = pbd_rrst_r;
                assign wrst = pbs_wrst_r;
                assign rq   = pbd_rrst_r;
                assign rqe  = pbd_rrst_r;
`endif
            end else begin : g_r
                // M9: the write side alone is reset
                rst_bridge pbs_rb (.clk(sclk), .arst_in(rq_s), .sync_in(s_por), .rst_out(wrst));
                assign rrst = d_por;
                sync_n #(.STAGES(2)) pbd_rq_s (.clk(dclk), .d(rq_s), .q(rq));
                assign rqe = rq;
            end
            wire we = s_run && !full && !wrst && s_lf[0];
            if (C13_SYNC) begin : g_sd
                always_ff @(posedge sclk)
                    if (wrst) pbs_data <= SEED;
                    else if (we) pbs_data <= prbs16_next(pbs_data);
            end else begin : g_ad
                always_ff @(posedge sclk or posedge wrst)
                    if (wrst) pbs_data <= SEED;
                    else if (we) pbs_data <= prbs16_next(pbs_data);
            end
            wire re = !empty && !rrst && d_lf[0];
            afifo16 #(.SYNC_RST(C13_SYNC)) u_fifo (.wclk(sclk), .wrst(wrst), .winc(we), .wdata(prbs16_next(pbs_data)), .wfull(full),
                            .rclk(dclk), .rrst(rrst), .rinc(re), .rdata(rdata), .rempty(empty));
            always_ff @(posedge dclk) begin
                pbd_v <= re;
                if (re) pbd_ramrd_w <= rdata;
                rqp <= rqe; arm <= rq && !rqp;
            end
            assign valid = pbd_v;
            assign w = pbd_ramrd_w;
        end
        chk_words #(.WDB(WDB)) u_chk (.clk(dclk), .valid(valid), .w(w), .arm(arm), .hold(d_hld), .e_err(e_err),
                                      .e_ev(e_ev), .e_relock(e_relock), .e_lock(e_lock));

    // ------------------------------------------------------------------ reset release and reset-domain crossing
    end else if (grp_of(VAR) == 4) begin : g_v
        logic rr, rqs, rb;
        logic [15:0] q0, q1;
        if (VAR == V_C12) begin : g_r
            rst_bridge pbd_rb (.clk(dclk), .arst_in(rq_d), .sync_in(d_por), .rst_out(rr));
            assign rb = rr;
            assign rqs = rr;                 // the checker sees the bridged request
            (* DONT_TOUCH = "TRUE" *) cff #(.W(16), .ASYNC(1'b0)) pbs_t (.clk(dclk), .arst(rr), .d(~q0), .q(q0));
            (* DONT_TOUCH = "TRUE" *) cff #(.W(16), .ASYNC(1'b0)) pbd_t (.clk(dclk), .arst(rr), .d(~q1), .q(q1));
        end else begin : g_r
            assign rr = rq_d;            // raw: released asynchronously to dclk (the flops start from INIT)
            // the checker's own view of the request, from a separate launch register (rq_d2)
            sync_n #(.STAGES(2)) pbd_rq_s (.clk(dclk), .d(rq_d2), .q(rqs));
            assign rb = 1'b0;
            (* DONT_TOUCH = "TRUE" *) cff #(.W(16), .INJREL(1'b1)) pbs_mut_t (.clk(dclk), .arst(rr), .d(~q0), .q(q0));
            (* DONT_TOUCH = "TRUE" *) cff #(.W(16), .INJREL(1'b1)) pbd_mut_t (.clk(dclk), .arst(rr), .d(~q1), .q(q1));
        end
        chk_coh u_chk (.clk(dclk), .q({q1, q0}), .rqs(rqs), .e_err(e_err), .e_ev(e_ev));
        assign e_lock = 1'b0;
        assign e_relock = 1'b0;

    end else begin : g_v
        // V_M8: the source domain's raw reset clears a destination datapath register, unqualified
        logic [15:0] r, pbd_lfd = '0;
        logic mp = 1'b0;
        logic [7:0] dv = '0;
        cff #(.W(16), .INJREL(1'b1)) pbd_mut_r (.clk(dclk), .arst(rq_s), .d(d_lf), .q(r));
        always_ff @(posedge dclk) begin
            pbd_lfd <= d_lf;
            mp      <= r != pbd_lfd;
            e_err   <= (r != pbd_lfd) && !mp;
            dv      <= dv + 1'b1;
            e_ev    <= dv == 0;
        end
        assign e_lock = 1'b0;
        assign e_relock = 1'b0;
    end
endmodule
