`timescale 1ns / 1ps
// rig_ctrl.sv: the rig's control and readout (design sections 4, 5 and 7), all built from correct crossings.
//
// uart_tx    8N1 transmitter, DIV clocks a bit.
// line_tx    formats one ASCII record and sends it with a CRC-8 (poly 0x07, init 0) over the characters before '*':
//              H,CDCRIG,<copies:3>,<build:8>*cc                     (once, after power-up)
//              E,<epoch:4>,<uptime_s:8>,<temp:3>,<vccint:3>,<cfgmclk:5>,<mode:1>*cc
//              C,<copy:3>,<variant:2>,<class:1>,<dir:1>,<errors:6>,<events:8>,<lockups:2>,<relocks:2>,<sat:1>*cc
//              S,TJ,<temp:3>,<uptime_s:8>*cc                         (every second after the temperature stop)
//            Every field is upper-case hex; temp and vccint are raw 12-bit XADC codes; cfgmclk is CFGMCLK cycles
//            per millisecond (kHz). host/read_counters.py decodes them.
// storm_gen  the reset-storm generator in clk_a (section 5).
// ro_dom     one destination domain's side of the epoch: quiesce, drain, freeze, and the bit-by-bit readout of
//            its rotating record chain over a toggle request / toggle acknowledge pair.
// dom_rdy    start-up gate (brief 11c): a domain is ready SETTLE cycles after its power-on reset is released.
// rig_epoch  the clk_a controller: seconds, epochs, the readout sequence, the temperature stop.

module uart_tx #(
    parameter int DIV = 868
) (
    input  logic       clk,
    input  logic       valid,
    input  logic [7:0] data,
    output logic       ready,
    output logic       tx
);
    logic [9:0]  sh = '1;
    logic [3:0]  n = '0;
    logic [15:0] c = '0;
    initial tx = 1'b1;
    assign ready = n == 0;
    always @(posedge clk)
        if (n == 0) begin
            tx <= 1'b1;
            if (valid) begin sh <= {1'b1, data, 1'b0}; n <= 4'd10; c <= '0; end
        end else if (c == 16'(DIV - 1)) begin
            c <= '0; n <= n - 1'b1;
        end else begin
            c <= c + 1'b1;
            tx <= sh[10 - n];
        end
endmodule

module line_tx (
    input  logic        clk,
    input  logic        start,
    input  logic [1:0]  kind,            // 0 H, 1 E, 2 C, 3 S
    input  logic [11:0] f_g,             // copy index / copy count (H)
    input  logic [4:0]  f_var,
    input  logic [1:0]  f_cls,
    input  logic [1:0]  f_dir,
    input  logic [72:0] f_rec,
    input  logic [15:0] f_epoch,
    input  logic [31:0] f_up,            // uptime / build id (H)
    input  logic [11:0] f_temp,
    input  logic [11:0] f_vcc,
    input  logic [19:0] f_khz,
    input  logic [1:0]  f_mode,
    output logic        busy,
    output logic        stb,
    output logic [7:0]  byte_o,
    input  logic        tx_ready
);
    localparam int L = 40;
    function automatic logic [7:0] hx(input logic [3:0] v);
        return v < 10 ? 8'h30 + v : 8'h37 + v;
    endfunction
    logic [8*L-1:0] lb;
    logic [5:0] len;
    always @* begin
        lb = '0; len = '0;
        case (kind)
            2'd0: begin
                lb[8*L-1 -: 8*21] = {"H,CDCRIG,", hx(f_g[11:8]), hx(f_g[7:4]), hx(f_g[3:0]), ",",
                                     hx(f_up[31:28]), hx(f_up[27:24]), hx(f_up[23:20]), hx(f_up[19:16]),
                                     hx(f_up[15:12]), hx(f_up[11:8]), hx(f_up[7:4]), hx(f_up[3:0])};
                len = 21;
            end
            2'd1: begin
                lb[8*L-1 -: 8*31] = {"E,", hx(f_epoch[15:12]), hx(f_epoch[11:8]), hx(f_epoch[7:4]), hx(f_epoch[3:0]), ",",
                                     hx(f_up[31:28]), hx(f_up[27:24]), hx(f_up[23:20]), hx(f_up[19:16]),
                                     hx(f_up[15:12]), hx(f_up[11:8]), hx(f_up[7:4]), hx(f_up[3:0]), ",",
                                     hx(f_temp[11:8]), hx(f_temp[7:4]), hx(f_temp[3:0]), ",",
                                     hx(f_vcc[11:8]), hx(f_vcc[7:4]), hx(f_vcc[3:0]), ",",
                                     hx(f_khz[19:16]), hx(f_khz[15:12]), hx(f_khz[11:8]), hx(f_khz[7:4]), hx(f_khz[3:0]),
                                     ",", hx({2'b00, f_mode})};
                len = 31;
            end
            2'd2: begin
                lb[8*L-1 -: 8*36] = {"C,", hx(f_g[11:8]), hx(f_g[7:4]), hx(f_g[3:0]), ",",
                                     hx({3'b000, f_var[4]}), hx(f_var[3:0]), ",", hx({2'b00, f_cls}), ",",
                                     hx({2'b00, f_dir}), ",",
                                     hx(f_rec[72:69]), hx(f_rec[68:65]), hx(f_rec[64:61]), hx(f_rec[60:57]),
                                     hx(f_rec[56:53]), hx(f_rec[52:49]), ",",
                                     hx(f_rec[48:45]), hx(f_rec[44:41]), hx(f_rec[40:37]), hx(f_rec[36:33]),
                                     hx(f_rec[32:29]), hx(f_rec[28:25]), hx(f_rec[24:21]), hx(f_rec[20:17]), ",",
                                     hx(f_rec[16:13]), hx(f_rec[12:9]), ",", hx(f_rec[8:5]), hx(f_rec[4:1]), ",",
                                     hx({3'b000, f_rec[0]})};
                len = 36;
            end
            default: begin
                lb[8*L-1 -: 8*17] = {"S,TJ,", hx(f_temp[11:8]), hx(f_temp[7:4]), hx(f_temp[3:0]), ",",
                                     hx(f_up[31:28]), hx(f_up[27:24]), hx(f_up[23:20]), hx(f_up[19:16]),
                                     hx(f_up[15:12]), hx(f_up[11:8]), hx(f_up[7:4]), hx(f_up[3:0])};
                len = 17;
            end
        endcase
    end
    logic [8*L-1:0] buf_r = '0;
    logic [5:0]  len_r = '0, i = '0;
    logic [2:0]  tail = '0;             // 0 body, 1 '*', 2 crc hi, 3 crc lo, 4 CR, 5 LF
    logic [7:0]  crc = '0;
    logic        act = 1'b0;
    function automatic logic [7:0] crc8(input logic [7:0] c, input logic [7:0] b);
        logic [7:0] x = c ^ b;
        for (int k = 0; k < 8; k++) x = x[7] ? (x << 1) ^ 8'h07 : x << 1;
        return x;
    endfunction
    wire [7:0] cur = i < len_r ? buf_r[8*L-1 - 8*i -: 8] :
                     tail == 1 ? "*" : tail == 2 ? hx(crc[7:4]) : tail == 3 ? hx(crc[3:0]) :
                     tail == 4 ? 8'h0D : 8'h0A;
    assign busy = act || start;
    always @(posedge clk) begin
        stb <= 1'b0;
        if (!act) begin
            if (start) begin buf_r <= lb; len_r <= len; i <= '0; tail <= '0; crc <= '0; act <= 1'b1; end
        end else if (tx_ready && !stb) begin
            stb <= 1'b1;
            byte_o <= cur;
            if (i < len_r) begin crc <= crc8(crc, cur); i <= i + 1'b1; if (i + 1'b1 == len_r) tail <= 3'd1; end
            else if (tail == 5) act <= 1'b0;
            else tail <= tail + 1'b1;
        end
    end
endmodule

module storm_gen #(
    parameter int MASKW = 17               // start probability 2^-MASKW per clk_a cycle (17: mean about 1.3 ms)
) (
    input  logic       clk,
    input  logic       en,
    input  logic [1:0] mode,                // 0 source side alone, 1 destination side alone, 2 both
    output logic       rq_s,
    output logic       rq_d,
    output logic       rq_any
);
    logic [30:0] lf = 31'h2B3C_4D5E;
    logic [15:0] gap = '0;
    logic [7:0]  hold = '0;
    logic        on = 1'b0;
    initial begin rq_s = 1'b0; rq_d = 1'b0; rq_any = 1'b0; end
    always @(posedge clk) begin
        lf <= {lf[29:0], lf[30] ^ lf[27]};             // PRBS-31
        if (on) begin
            if (hold == 0) begin on <= 1'b0; rq_s <= 1'b0; rq_d <= 1'b0; rq_any <= 1'b0; gap <= '0; end
            else hold <= hold - 1'b1;
        end else begin
            if (gap != 16'hFFFF) gap <= gap + 1'b1;
            // at least 64 cycles apart; held 50-177 clk_a cycles (16-64 cycles of CFGMCLK at its slowest)
            if (en && gap >= 64 && lf[MASKW-1:0] == 0) begin
                on <= 1'b1; hold <= 8'd50 + {1'b0, lf[22:16]};
                rq_s <= mode != 2'd1; rq_d <= mode != 2'd0; rq_any <= 1'b1;
            end
        end
    end
endmodule

// A domain is ready SETTLE cycles after its power-on reset has been released, in its own clock. rig_core holds the
// sources off (the quiesce request) until every domain is ready, so no checker sees traffic before both of its
// domains are running: clk_c, the MMCM output, starts tens of microseconds after clk_a, and the first board runs
// counted the events the sources had already sent as one error in every a->c copy (brief 11c, finding 1).
module dom_rdy #(
    parameter int SETTLE = 255
) (
    input  logic clk,
    input  logic por,
    output logic rdy
);
    logic [7:0] n = '0;
    initial rdy = 1'b0;
    always @(posedge clk)
        if (por) begin n <= '0; rdy <= 1'b0; end
        else if (n == 8'(SETTLE)) rdy <= 1'b1;
        else n <= n + 1'b1;
endmodule

module ro_dom #(
    parameter int DRAIN = 1024
) (
    input  logic clk,
    input  logic q_req_a,          // clk_a register
    input  logic sh_tgl_a,         // clk_a register
    input  logic tap,              // the chain's head bit
    output logic run,
    output logic hold,
    output logic frz,
    output logic sh,
    output logic bit_o,            // to clk_a
    output logic ack_o             // to clk_a
);
    logic q, t, tp = 1'b0;
    logic [15:0] dc = '0;
    logic [2:0]  w = '0;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(0)) u_q (.src_clk(1'b0), .src_in(q_req_a), .dest_clk(clk), .dest_out(q));
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(0)) u_t (.src_clk(1'b0), .src_in(sh_tgl_a), .dest_clk(clk), .dest_out(t));
    initial begin frz = 1'b0; sh = 1'b0; bit_o = 1'b0; ack_o = 1'b0; end
    assign run = !q;
    assign hold = q;
    always @(posedge clk) begin
        sh <= 1'b0;
        tp <= t;
        if (!q) begin dc <= '0; frz <= 1'b0; end
        else if (dc != 16'(DRAIN)) dc <= dc + 1'b1;
        else frz <= 1'b1;
        if (frz && t != tp) begin bit_o <= tap; sh <= 1'b1; w <= 3'd6; end
        else if (w != 0) begin w <= w - 1'b1; if (w == 1) ack_o <= ~ack_o; end
    end
endmodule

module rig_epoch #(
    parameter int NTOT          = 28,
    parameter int TICK          = 100_000_000,    // clk_a cycles a second
    parameter int EPOCH_S       = 60,
    parameter int STORM_DELAY_S = 600,
    parameter int TJ_STOP       = 2871,           // XADC code for 80 degC: (80 + 273.15) * 4096 / 503.975
    parameter logic [31:0] BUILD_ID = 32'h0
) (
    input  logic        clk,
    input  logic        por,
    input  logic [2:0]  frz_s,           // synchronised into clk_a
    input  logic [2:0]  bit_s,
    input  logic [2:0]  ack_s,
    input  logic [11:0] temp,
    input  logic [11:0] vcc,
    input  logic [19:0] khz,
    output logic [11:0] g,               // copy index being read; the ROMs answer below
    input  logic [1:0]  g_dom,
    input  logic [4:0]  g_var,
    input  logic [1:0]  g_cls,
    input  logic [1:0]  g_dir,
    output logic        q_req,
    output logic [2:0]  sh_tgl,
    output logic        storm_en,
    output logic [1:0]  mode,
    output logic        clkc_off,
    output logic        stopped,
    // to line_tx
    output logic        p_start,
    output logic [1:0]  p_kind,
    output logic [72:0] p_rec,
    output logic [15:0] p_epoch,
    output logic [31:0] p_up,
    input  logic        p_busy
);
    logic [31:0] tick = '0, up = '0;
    logic [15:0] esec = '0, epoch = '0;
    logic        sec = 1'b0, due = 1'b0, hot1 = 1'b0, stop_req = 1'b0, final_rd = 1'b0;
    logic [2:0]  ackp = '0;
    logic [1:0]  dom = '0;
    logic [6:0]  nb = '0;
    typedef enum logic [3:0] {S_BOOT, S_HELLO, S_IDLE, S_FRZ, S_E, S_SCAN, S_REQ, S_ACK, S_C, S_NEXT, S_END,
                              S_STOP, S_STOPPED} st_t;
    st_t st = S_BOOT;
    initial begin q_req = 1'b0; sh_tgl = '0; clkc_off = 1'b0; stopped = 1'b0; mode = '0; p_start = 1'b0; end

    always @(posedge clk) begin
        sec <= 1'b0;
        if (tick == 32'(TICK - 1)) begin tick <= '0; sec <= 1'b1; end else tick <= tick + 1'b1;
        if (sec) begin
            up <= up + 1'b1;
            if (esec == 16'(EPOCH_S - 1)) begin esec <= '0; due <= 1'b1; end else esec <= esec + 1'b1;
            hot1 <= temp >= 12'(TJ_STOP);
            if (hot1 && temp >= 12'(TJ_STOP)) stop_req <= 1'b1;
        end
        // an epoch is EPOCH_S seconds of traffic: the count restarts when a readout ends
        if (st == S_FRZ) due <= 1'b0;
        if (st == S_END) begin esec <= '0; due <= 1'b0; end
    end
    assign storm_en = up >= 32'(STORM_DELAY_S) && !q_req && !stopped;

    always @(posedge clk) begin
        p_start <= 1'b0;
        case (st)
            S_BOOT:  if (!por) st <= S_HELLO;
            S_HELLO: if (!p_busy) begin p_kind <= 2'd0; p_up <= BUILD_ID; p_start <= 1'b1; st <= S_IDLE; end
            S_IDLE:
                if (stop_req) begin final_rd <= 1'b1; q_req <= 1'b1; st <= S_FRZ; end
                else if (due) begin q_req <= 1'b1; st <= S_FRZ; end
            S_FRZ:   if (&frz_s && !p_busy) begin
                         p_kind <= 2'd1; p_epoch <= epoch; p_up <= up; p_start <= 1'b1;
                         dom <= '0; g <= 12'(NTOT - 1); st <= S_SCAN;
                     end
            S_SCAN:  if (g_dom == dom) begin nb <= '0; st <= S_REQ; end else st <= S_NEXT;
            S_REQ:   begin sh_tgl[dom] <= ~sh_tgl[dom]; st <= S_ACK; end
            S_ACK:   if (ack_s[dom] != ackp[dom]) begin
                         ackp[dom] <= ack_s[dom];
                         p_rec <= {p_rec[71:0], bit_s[dom]};
                         nb <= nb + 1'b1;
                         st <= nb == 7'd72 ? S_C : S_REQ;
                     end
            S_C:     if (!p_busy) begin p_kind <= 2'd2; p_start <= 1'b1; st <= S_NEXT; end
            S_NEXT:  if (!p_busy && !p_start) begin
                         if (g == 0) begin
                             if (dom == 2'd2) st <= S_END;
                             else begin dom <= dom + 1'b1; g <= 12'(NTOT - 1); st <= S_SCAN; end
                         end else begin g <= g - 1'b1; st <= S_SCAN; end
                     end
            S_END:   if (!p_busy) begin
                         epoch <= epoch + 1'b1;
                         mode <= mode == 2'd2 ? 2'd0 : mode + 1'b1;
                         if (final_rd) begin stopped <= 1'b1; clkc_off <= 1'b1; st <= S_STOPPED; end
                         else begin q_req <= 1'b0; st <= S_IDLE; end
                     end
            S_STOPPED: if (sec && !p_busy) begin p_kind <= 2'd3; p_up <= up; p_start <= 1'b1; end
            default: st <= S_IDLE;
        endcase
    end
endmodule
