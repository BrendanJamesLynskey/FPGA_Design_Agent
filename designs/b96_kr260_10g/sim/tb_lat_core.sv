`timescale 1ns/1fs
// tb_lat_core.sv (brief 96E): the whole core's tick-to-trade in xsim with AMD's real XPM macros, at a chosen phase between the receive and transmit user clocks
// (sim/gth_wiz_model96e.sv, compile with -d RXPH=<ns>). The same measurement as tests/core_cocotb.py::tick_to_trade_digital (8 orders, 301 clocks apart), written in SystemVerilog so
// xsim can run it, with one more strobe: the clock at which tx_path's rx_sop_p (the receive-start stamp that E and L are made of on the board) fires for the feed frame.
// Prints one line per order: "ORD <n> x_start <ns> x_price <ns> y_price <ns> w7_mac <ns> fire <ns> go <ns> sop_mac <ns> rxsop <ns>" (y_price is 0 for RATE_MATCH = 0).
// Times are absolute ns of the clock edge that LOADS the signal (a value seen just after the edge). Post-processed by results/b96e/core_lat.py.
module tb_lat_core #(
    parameter bit RATE_MATCH = 1'b1,
    parameter bit RM_OWN = 1'b0,
    parameter int NORD = 8
);
    localparam real TREF = 6.2058;
    logic clk = 1'b0, refclk = 1'b0, rst = 1'b1;
    logic h_we = 1'b0, h_re = 1'b0;
    logic [11:0] h_addr = '0;
    logic [31:0] h_wdata = '0, h_rdata;
    logic sfp_tx_disable, tx_p, tx_n, scl_low, sda_low, sm_en;
    logic [1:0] led;
    logic [7:0] sm_addr;
    always #5.0 clk = ~clk;
    always #(TREF / 2.0) refclk = ~refclk;
    b96_core #(.BUILD_STAMP(32'h96), .NEAR_END(1'b1), .TRADE(1'b1), .RATE_MATCH(RATE_MATCH), .RM_OWN(RM_OWN)) u (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata, .refclk,
        .rx_p(1'b0), .rx_n(1'b1), .tx_p, .tx_n, .sfp_tx_disable, .sfp_mod_abs(1'b0), .sfp_rx_los(1'b0), .sfp_tx_fault(1'b0),
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .sm_en, .sm_addr, .sm_do(16'h0), .sm_rdy(sm_en), .led);

    task automatic hw(input [11:0] a, input [31:0] d);
        h_addr = a; h_wdata = d; h_we = 1'b1; @(posedge clk); h_we = 1'b0; @(posedge clk);
    endtask
    task automatic hr(input [11:0] a, output [31:0] d);
        h_addr = a; h_re = 1'b1; @(posedge clk); h_re = 1'b0; @(posedge clk); @(posedge clk); #1; d = h_rdata;
    endtask

    // ---------------------------------------------------------------- the monitors (hierarchical references into the selected receive path)
    logic        x_v, x_s, y_v, m_v, fire, go_p, sop, rxsop_p;
    logic [7:0]  x_c, y_c;
    logic [63:0] x_d, y_d;
    logic [3:0]  td_wi;
    logic        td_feed, kind0;
    logic        rxclk, txclk;
    assign txclk = u.txusr2; assign rxclk = u.rxusr2;
    if (RATE_MATCH) begin : g_m
        assign x_v = u.g_rm.u_rx.x_v; assign x_c = u.g_rm.u_rx.x_c; assign x_d = u.g_rm.u_rx.x_d;
        assign y_v = u.g_rm.u_rx.y_v; assign y_c = u.g_rm.u_rx.y_c; assign y_d = u.g_rm.u_rx.y_d;
        assign m_v = u.g_rm.u_rx.m_v; assign td_wi = u.g_rm.u_rx.u_td.wi; assign td_feed = u.g_rm.u_rx.u_td.is_feed; assign fire = u.g_rm.u_rx.u_td.fire;
        assign go_p = u.g_rm.u_tx.go_p; assign sop = u.g_rm.u_tx.sop; assign kind0 = (u.g_rm.u_tx.cur_kind == 0); assign rxsop_p = u.g_rm.u_tx.rx_sop_p;
    end else begin : g_m
        assign x_v = u.g_old.u_rx.x_v; assign x_c = u.g_old.u_rx.x_c; assign x_d = u.g_old.u_rx.x_d;
        assign y_v = 1'b0; assign y_c = '0; assign y_d = '0;
        assign m_v = u.g_old.u_rx.m_v; assign td_wi = u.g_old.u_rx.u_td.wi; assign td_feed = u.g_old.u_rx.u_td.is_feed; assign fire = u.g_old.u_rx.u_td.fire;
        assign go_p = u.g_old.u_tx.go_p; assign sop = u.g_old.u_tx.sop; assign kind0 = (u.g_old.u_tx.cur_kind == 0); assign rxsop_p = u.g_old.u_tx.rx_sop_p;
    end

    real t_x_start, t_x_price, t_y_price, t_w7, t_fire, t_go, t_sop, t_rxsop, quiet_until;
    int  nbx, nby, nord;
    logic have_x, have_y, have_w7, have_fire, have_go, have_rxsop;
    initial begin quiet_until = 0.0; nbx = -1; nby = -1; nord = 0; have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; t_x_start = 0; t_y_price = 0; t_rxsop = 0; end
    // receive clock: the PCS output register and the buffer's output (RATE_MATCH = 1 loads y in the transmit clock: sampled below)
    always @(posedge rxclk) begin
        real t;
        t = $realtime;
        #0.05;
        if (x_v && t > quiet_until) begin
            if ((x_c == 8'h01 && x_d[7:0] == 8'hFB) || (x_c == 8'h1F && x_d[39:32] == 8'hFB)) begin nbx = 0; t_x_start = t; have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; end
            else if (nbx >= 0) nbx = nbx + 1;
            if (nbx == 8 && !have_x) begin t_x_price = t; have_x = 1; $display("DBG x_price %0.3f", t); end
        end
        if (!RATE_MATCH && have_x && !have_w7 && m_v && td_wi == 7 && td_feed) begin t_w7 = t; have_w7 = 1; end
        if (!RATE_MATCH && have_w7 && !have_fire && fire) begin t_fire = t; have_fire = 1; end
    end
    always @(posedge txclk) begin
        real t;
        t = $realtime;
        #0.05;
        if (RATE_MATCH && y_v) begin
            if ((y_c == 8'h01 && y_d[7:0] == 8'hFB) || (y_c == 8'h1F && y_d[39:32] == 8'hFB)) nby = 0;
            else if (nby >= 0) nby = nby + 1;
            if (nby == 8 && have_x && !have_y) begin t_y_price = t; have_y = 1; end
        end
        if (RATE_MATCH && have_x && !have_w7 && m_v && td_wi == 7 && td_feed) begin t_w7 = t; have_w7 = 1; end
        if (RATE_MATCH && have_w7 && !have_fire && fire) begin t_fire = t; have_fire = 1; end
        if (have_x && !have_rxsop && rxsop_p) begin t_rxsop = t; have_rxsop = 1; end
        if (have_fire && !have_go && go_p) begin t_go = t; have_go = 1; end
        if (have_go && sop && kind0) begin
            t_sop = t;
            $display("ORD %0d x_start %0.3f x_price %0.3f y_price %0.3f w7_mac %0.3f fire %0.3f go %0.3f sop_mac %0.3f rxsop %0.3f", nord, t_x_start, t_x_price, t_y_price, t_w7, t_fire, t_go, t_sop, t_rxsop);
            nord = nord + 1;
            have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; nbx = -1; nby = -1;
            quiet_until = t + 150.0 * TREF;
            if (nord == NORD) begin $display("DONE orders %0d", nord); $finish; end
        end
    end
    // ---------------------------------------------------------------- the run
    logic [31:0] st;
    initial begin
        repeat (6) @(posedge clk);
        rst = 1'b0;
        st = 0;
        for (int i = 0; i < 400 && !((st & 1) && (st & 2) && (st & 32'h200)); i++) begin
            #200; hr(12'h014, st);
        end
        if (!((st & 1) && (st & 2) && (st & 32'h200))) begin $display("LINK DID NOT COME UP: GTSTAT %h", st); $finish; end
        $display("LINK UP at %0t", $time);
        hw(12'h018, 1);
        hw(12'h060, 9975); hw(12'h064, 100);
        hw(12'h06C, (1 << 16) | 66);
        hw(12'h068, 32'h1 | 32'h4 | (1 << 4));
        hw(12'h070, 9950); hw(12'h074, 301); hw(12'h078, NORD);
        hw(12'h018, 2);
        #(9000.0 * TREF * 4);
        hw(12'h018, 4); #3000;
        hr(12'h000, st); $display("ID %h", st);
        hr(12'h008, st); $display("FEATURES %h", st);
        hr(12'h014, st); $display("GTSTAT %h", st);
        hr(12'h060, st); $display("thr %0d", st);
        hr(12'h068, st); $display("mode %h", st);
        hr(12'h200 + 4 * 25, st); $display("ts %0d", st);
        hr(12'h200 + 4 * 0, st); $display("n_order %0d", st);
        hr(12'h200 + 4 * 1, st); $display("n_feed %0d", st);
        hr(12'h100 + 4 * 11, st); $display("rx n_fired %0d", st);
        $display("TIMEOUT orders %0d", nord);
        $finish;
    end
endmodule
