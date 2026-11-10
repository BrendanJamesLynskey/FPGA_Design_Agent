`timescale 1ns / 1ps
// rig_core.sv: the whole rig without the FPGA primitives (clocks, XADC): every copy, the three record chains, the
// epoch controller, the reset storms, the CFGMCLK meter and the UART. rig_top.sv wraps it for the Nexys A7;
// the simulation drives it directly.
//
// Copy counts: one parameter per variant (N_<variant>). The small build sets them all to 1; the full build uses
// 352 (tcl/rig_map.tcl; the design's 536 did not fit). Copies are numbered g = 0..NTOT-1 in variant order.

module rig_core #(
    parameter int N_C1 = 1, N_C2 = 1, N_C3A = 1, N_C3B = 1, N_C4 = 1, N_C5 = 1, N_C6 = 1, N_C7 = 1,
    parameter int N_C8 = 1, N_C9 = 1, N_C10 = 1, N_C11 = 1, N_C12 = 1, N_C13 = 1,
    parameter int N_M1 = 1, N_M1B = 1, N_M2 = 1, N_M3 = 1, N_M4 = 1, N_M5 = 1, N_M6A = 1, N_M6B = 1,
    parameter int N_M6C = 1, N_M7 = 1, N_M8 = 1, N_M9 = 1, N_M10 = 1, N_M11 = 1,
    parameter int TICK          = 100_000_000,
    parameter int MS_TICKS      = 100_000,
    parameter int EPOCH_S       = 60,
    parameter int STORM_DELAY_S = 600,
    parameter int STORM_MASKW   = 17,
    parameter int UART_DIV      = 868,
    parameter int DRAIN         = 1024,
    parameter int WDB           = 16,
    parameter int SETTLE        = 255,          // start-up: cycles a domain settles after its reset (dom_rdy)
    parameter int TJ_STOP       = 2871,
    parameter logic [31:0] BUILD_ID = 32'h0
) (
    input  logic        clk_a,
    input  logic        clk_b,
    input  logic        clk_c,
    input  logic        clk_f,
    input  logic        locked,          // MMCM (clk_c, clk_f)
    input  logic [11:0] temp,            // XADC codes
    input  logic [11:0] vcc,
    output logic        uart_txd,
    output logic        clkc_off,
    output logic [3:0]  led,
    output logic        tx_stb,          // the byte stream before the UART (simulation taps it)
    output logic [7:0]  tx_byte
);
    import rig_pkg::*;

    function automatic int ncnt(input int v);
        case (v)
            V_C1: return N_C1;   V_C2: return N_C2;   V_C3A: return N_C3A; V_C3B: return N_C3B;
            V_C4: return N_C4;   V_C5: return N_C5;   V_C6: return N_C6;   V_C7: return N_C7;
            V_C8: return N_C8;   V_C9: return N_C9;   V_C10: return N_C10; V_C11: return N_C11;
            V_C12: return N_C12; V_C13: return N_C13;
            V_M1: return N_M1;   V_M1B: return N_M1B; V_M2: return N_M2;   V_M3: return N_M3;
            V_M4: return N_M4;   V_M5: return N_M5;   V_M6A: return N_M6A; V_M6B: return N_M6B;
            V_M6C: return N_M6C; V_M7: return N_M7;   V_M8: return N_M8;   V_M9: return N_M9;
            V_M10: return N_M10; default: return N_M11;
        endcase
    endfunction
    // (Icarus accepts these as constant functions only with the loop variable declared outside the loop)
    function automatic int ntot_f(input int dummy);
        int n, v;
        n = 0;
        for (v = 0; v < NVAR; v = v + 1) n = n + ncnt(v);
        return n;
    endfunction
    function automatic int var_of(input int g);
        int acc, v;
        acc = 0;
        for (v = 0; v < NVAR; v = v + 1) begin
            if (g < acc + ncnt(v)) return v;
            acc = acc + ncnt(v);
        end
        return 0;
    endfunction
    function automatic int k_of(input int g);
        int acc, v;
        acc = 0;
        for (v = 0; v < NVAR; v = v + 1) begin
            if (g < acc + ncnt(v)) return g - acc;
            acc = acc + ncnt(v);
        end
        return 0;
    endfunction
    // a local copy of rig_pkg::ddom (Icarus: a constant function may call only functions of its own module)
    function automatic int ddom_l(input int v, input int k);
        if (v == V_M6B || v == V_M6C) return D_B;
        if (k % 3 == 0) return D_B;
        if (k % 3 == 1) return D_A;
        return D_C;
    endfunction
    function automatic int ndom(input int d);
        int n, g;
        n = 0;
        for (g = 0; g < ntot_f(0); g = g + 1) if (ddom_l(var_of(g), k_of(g)) == d) n = n + 1;
        return n;
    endfunction
    localparam int NTOT = ntot_f(0);
    localparam int NA = ndom(D_A), NB = ndom(D_B), NC = ndom(D_C);

    // ---------------------------------------------------------------- power-on resets, one per domain
    logic [7:0] pc = '0;
    logic por_a = 1'b1, por_b, por_c, por_f;
    always_ff @(posedge clk_a)
        if (pc != 8'hFF) pc <= pc + 1'b1;
        else por_a <= 1'b0;
    rst_bridge u_por_b (.clk(clk_b), .arst_in(por_a), .sync_in(1'b0), .rst_out(por_b));
    // por_a and the MMCM's LOCKED are bridged separately, chained through the second bridge's D input
    logic lk_c, lk_f;
    rst_bridge u_lock_c (.clk(clk_c), .arst_in(!locked), .sync_in(1'b0), .rst_out(lk_c));
    rst_bridge u_por_c  (.clk(clk_c), .arst_in(por_a), .sync_in(lk_c), .rst_out(por_c));
    rst_bridge u_lock_f (.clk(clk_f), .arst_in(!locked), .sync_in(1'b0), .rst_out(lk_f));
    rst_bridge u_por_f  (.clk(clk_f), .arst_in(por_a), .sync_in(lk_f), .rst_out(por_f));

    // ---------------------------------------------------------------- start-up gate
    // Every domain reports ready (its reset released and SETTLE cycles gone) to clk_a; until all four have, the
    // sources are held off through the same quiesce request the epochs use, so no checker counts before both of
    // its domains are running and settled (brief 11c). Nothing is masked afterwards.
    logic [3:0] rdy_x, rdy_s;
    dom_rdy #(.SETTLE(SETTLE)) u_rdy_a (.clk(clk_a), .por(por_a), .rdy(rdy_x[0]));
    dom_rdy #(.SETTLE(SETTLE)) u_rdy_b (.clk(clk_b), .por(por_b), .rdy(rdy_x[1]));
    dom_rdy #(.SETTLE(SETTLE)) u_rdy_c (.clk(clk_c), .por(por_c), .rdy(rdy_x[2]));
    dom_rdy #(.SETTLE(SETTLE)) u_rdy_f (.clk(clk_f), .por(por_f), .rdy(rdy_x[3]));
    assign rdy_s[0] = rdy_x[0];
    for (genvar d = 1; d < 4; d++) begin : g_rdy
        wire dclk = d == 1 ? clk_b : d == 2 ? clk_c : clk_f;
        xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(1)) u_r (.src_clk(dclk), .src_in(rdy_x[d]), .dest_clk(clk_a), .dest_out(rdy_s[d]));
    end
    logic q_req, storm_en, stopped;
    logic q_run = 1'b1;
`ifdef CDC_NO_STARTUP_GATE
    always_ff @(posedge clk_a) q_run <= q_req;                    // simulation only: the first boards' behaviour
`else
    always_ff @(posedge clk_a) q_run <= q_req || !(&rdy_s);      // a clk_a register, as ro_dom expects
`endif

    // ---------------------------------------------------------------- epoch control and readout
    logic [2:0] sh_tgl, frz_s, bit_s, ack_s;
    logic [1:0] mode;
    logic [11:0] g;
    wire  [1:0] dom_rom [NTOT];
    wire  [4:0] var_rom [NTOT];
    wire  [1:0] cls_rom [NTOT];
    wire  [1:0] dir_rom [NTOT];
    wire  [11:0] gi = g < NTOT ? g : 12'd0;

    logic run_a, run_b, run_c, run_f, hold_a, hold_b, hold_c, frz_a, frz_b, frz_c, sh_a, sh_b, sh_c;
    wire  [NTOT:0] cha, chb, chc;           // wire: one driver per bit (Icarus merges a logic vector's drivers)
    logic [2:0] bit_x, ack_x, frz_x;
    ro_dom #(.DRAIN(DRAIN)) u_ro_a (.clk(clk_a), .q_req_a(q_run), .sh_tgl_a(sh_tgl[0]), .tap(cha[NTOT]),
        .run(run_a), .hold(hold_a), .frz(frz_a), .sh(sh_a), .bit_o(bit_x[0]), .ack_o(ack_x[0]));
    ro_dom #(.DRAIN(DRAIN)) u_ro_b (.clk(clk_b), .q_req_a(q_run), .sh_tgl_a(sh_tgl[1]), .tap(chb[NTOT]),
        .run(run_b), .hold(hold_b), .frz(frz_b), .sh(sh_b), .bit_o(bit_x[1]), .ack_o(ack_x[1]));
    ro_dom #(.DRAIN(DRAIN)) u_ro_c (.clk(clk_c), .q_req_a(q_run), .sh_tgl_a(sh_tgl[2]), .tap(chc[NTOT]),
        .run(run_c), .hold(hold_c), .frz(frz_c), .sh(sh_c), .bit_o(bit_x[2]), .ack_o(ack_x[2]));
    assign frz_x = {frz_c, frz_b, frz_a};
    for (genvar d = 0; d < 3; d++) begin : g_back
        wire dclk = d == 0 ? clk_a : d == 1 ? clk_b : clk_c;
        xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(1)) u_f (.src_clk(dclk), .src_in(frz_x[d]), .dest_clk(clk_a), .dest_out(frz_s[d]));
        xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(1)) u_b (.src_clk(dclk), .src_in(bit_x[d]), .dest_clk(clk_a), .dest_out(bit_s[d]));
        xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(1)) u_k (.src_clk(dclk), .src_in(ack_x[d]), .dest_clk(clk_a), .dest_out(ack_s[d]));
    end
    logic qf;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(0)) u_qf (.src_clk(1'b0), .src_in(q_run), .dest_clk(clk_f), .dest_out(qf));
    assign run_f = !qf;

    // CFGMCLK meter: clk_b cycles per MS_TICKS clk_a cycles (per millisecond = kHz in hardware)
    logic [19:0] bc = '0, bca, bcp = '0, khz = '0;
    logic [31:0] mc = '0;
    always_ff @(posedge clk_b) bc <= bc + 1'b1;
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .WIDTH(20), .REG_OUTPUT(1)) u_bmeter (.src_clk(clk_b), .src_in_bin(bc), .dest_clk(clk_a), .dest_out_bin(bca));
    always_ff @(posedge clk_a)
        if (mc == 32'(MS_TICKS - 1)) begin mc <= '0; khz <= bca - bcp; bcp <= bca; end
        else mc <= mc + 1'b1;

    // reset storms
    logic rq_s, rq_d, rq_any;
    storm_gen #(.MASKW(STORM_MASKW)) u_storm (.clk(clk_a), .en(storm_en), .mode(mode), .rq_s(rq_s), .rq_d(rq_d), .rq_any(rq_any));

    // printer and UART
    logic p_start, p_busy, p_stb, tx_ready;
    logic [1:0] p_kind;
    logic [72:0] p_rec;
    logic [15:0] p_epoch;
    logic [31:0] p_up;
    logic [7:0] p_byte;
    rig_epoch #(.NTOT(NTOT), .TICK(TICK), .EPOCH_S(EPOCH_S), .STORM_DELAY_S(STORM_DELAY_S), .TJ_STOP(TJ_STOP),
                .BUILD_ID(BUILD_ID))
        u_epoch (.clk(clk_a), .por(por_a), .frz_s(frz_s), .bit_s(bit_s), .ack_s(ack_s), .temp(temp), .vcc(vcc),
                 .khz(khz), .g(g), .g_dom(dom_rom[gi]), .g_var(var_rom[gi]), .g_cls(cls_rom[gi]),
                 .g_dir(dir_rom[gi]), .q_req(q_req), .sh_tgl(sh_tgl), .storm_en(storm_en), .mode(mode),
                 .clkc_off(clkc_off), .stopped(stopped), .p_start(p_start), .p_kind(p_kind), .p_rec(p_rec),
                 .p_epoch(p_epoch), .p_up(p_up), .p_busy(p_busy));
    line_tx u_line (.clk(clk_a), .start(p_start), .kind(p_kind), .f_g(p_kind == 2'd0 ? 12'(NTOT) : g),
                    .f_var(var_rom[gi]), .f_cls(cls_rom[gi]), .f_dir(dir_rom[gi]), .f_rec(p_rec),
                    .f_epoch(p_epoch), .f_up(p_up), .f_temp(temp), .f_vcc(vcc), .f_khz(khz), .f_mode(mode),
                    .busy(p_busy), .stb(p_stb), .byte_o(p_byte), .tx_ready(tx_ready));
    uart_tx #(.DIV(UART_DIV)) u_uart (.clk(clk_a), .valid(p_stb), .data(p_byte), .ready(tx_ready), .tx(uart_txd));
    assign tx_stb = p_stb;
    assign tx_byte = p_byte;

    // status LEDs: heartbeat, readout in progress, storms enabled, stopped on temperature
    logic [25:0] hb = '0;
    always_ff @(posedge clk_a) hb <= hb + 1'b1;
    assign led = {stopped, storm_en, q_req, hb[25]};

    // ---------------------------------------------------------------- the copies
    for (genvar gg = 0; gg < NTOT; gg++) begin : g_copy
        localparam int V  = var_of(gg);
        localparam int KK = k_of(gg);
        localparam int DG = ddom_l(V, KK);
        localparam bit IN_A = DG == 0, IN_B = DG == 1, IN_C = DG == 2;
        logic so;
        // stormed variants (C11-C13, M8-M11) get their own copies of the storm requests, so each copy's bridge or
        // synchroniser has its own launch flop (no fan-out of one flop into many synchronisers)
        localparam bit ST = V == 11 || V == 12 || V == 13 || V == 24 || V == 25 || V == 26 || V == 27;
        logic c_rqs, c_rqd, c_rqa, c_rqd2;
        if (ST) begin : g_rq
            (* DONT_TOUCH = "TRUE" *) logic rs = 1'b0, rd = 1'b0, ra = 1'b0, rd2 = 1'b0;
            always_ff @(posedge clk_a) begin rs <= rq_s; rd <= rq_d; ra <= rq_any; rd2 <= rq_d; end
            assign c_rqs = rs; assign c_rqd = rd; assign c_rqa = ra; assign c_rqd2 = rd2;
        end else begin : g_norq
            assign c_rqs = 1'b0; assign c_rqd = 1'b0; assign c_rqa = 1'b0; assign c_rqd2 = 1'b0;
        end
        (* keep_hierarchy = "yes" *)
        rig_copy #(.VAR(V), .K(KK), .G(gg), .WDB(WDB)) u_copy (
            .clk_a(clk_a), .clk_b(clk_b), .clk_c(clk_c), .clk_f(clk_f),
            .por_a(por_a), .por_b(por_b), .por_c(por_c), .por_f(por_f),
            .run_a(run_a), .run_b(run_b), .run_c(run_c), .run_f(run_f),
            .hold_a(hold_a), .hold_b(hold_b), .hold_c(hold_c), .frz_a(frz_a), .frz_b(frz_b), .frz_c(frz_c),
            .sh_a(sh_a), .sh_b(sh_b), .sh_c(sh_c),
            .sin(IN_A ? cha[gg] : IN_B ? chb[gg] : chc[gg]), .sout(so),
            .rq_s(c_rqs), .rq_d(c_rqd), .rq_any(c_rqa), .rq_d2(c_rqd2));
        assign cha[gg+1] = IN_A ? so : cha[gg];
        assign chb[gg+1] = IN_B ? so : chb[gg];
        assign chc[gg+1] = IN_C ? so : chc[gg];
        assign dom_rom[gg] = 2'(DG);
        assign var_rom[gg] = 5'(V);
        assign cls_rom[gg] = 2'((KK + KK / 3) % 3);
        assign dir_rom[gg] = 2'(KK % 3);
    end
    // each chain closes on itself (a domain without copies has an empty chain)
    assign cha[0] = NA > 0 ? cha[NTOT] : 1'b0;
    assign chb[0] = NB > 0 ? chb[NTOT] : 1'b0;
    assign chc[0] = NC > 0 ? chc[NTOT] : 1'b0;
endmodule
