`timescale 1ns/1fs
// tb_ml_core.sv (brief 113): the whole core in xsim with AMD's real XPM macros and a SYNTHETIC FEED injected on the receive words (gth_wiz_model113.sv: u.u_gt.inj_en / inj_d).
// The words come from the Python PCS model (rm_gp_ml/model/stream.py writes words.hex: one 64-bit word a line, the first word at receive clock 0) and are played one a receive clock.
// Compile with -d ML=1 for build rm_gp_ml (prints the ML stage's per-message lines and registers); without it for the unmodified rm_gp core (prints only the order timing), so the
// two can be measured with the same stimulus. +WORDS=<file> +NW=<words> +VETO=<0|1> +INST=<tracked instrument> +RXPH=<ns> (compile -d RXPH=).
// Prints, one line each:  MSG <n> trk <b> feat <hex> cls <c> ok <b> agree <b> hit <b> dec <b> veto <b> type <t> side <s> px <p> sz <z>   (at the price word of every frame the rule path accepts, mid-clock)
//                         FIRE <n>                                          (the rule path's order decision, mid-clock of the clock it is registered)
//                         ORD <k> x_start .. rxsop ..                      (as tb_lat_core.sv: the times of the latency chain, for results/b96e/core_lat.py)
//                         REG <name> <value>                               (the counters read through the host bus at the end)
module tb_ml_core #(
    parameter bit RATE_MATCH = 1'b1,
    parameter bit RM_OWN = 1'b1,
    parameter int ML_HOLD = 0
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
`ifdef ML
    b96_core #(.BUILD_STAMP(32'h113), .NEAR_END(1'b1), .TRADE(1'b1), .RATE_MATCH(RATE_MATCH), .RM_OWN(RM_OWN), .ML_HOLD(ML_HOLD)) u (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata, .refclk,
`else
    b96_core #(.BUILD_STAMP(32'h113), .NEAR_END(1'b1), .TRADE(1'b1), .RATE_MATCH(RATE_MATCH), .RM_OWN(RM_OWN)) u (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata, .refclk,
`endif
        .rx_p(1'b0), .rx_n(1'b1), .tx_p, .tx_n, .sfp_tx_disable, .sfp_mod_abs(1'b0), .sfp_rx_los(1'b0), .sfp_tx_fault(1'b0),
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .sm_en, .sm_addr, .sm_do(16'h0), .sm_rdy(sm_en), .led);

    task automatic hw(input [11:0] a, input [31:0] d);
        h_addr = a; h_wdata = d; h_we = 1'b1; @(posedge clk); #1; h_we = 1'b0; @(posedge clk); #1;      // changes 1 ns after the edge: no race with the core's sampling (tb_lat_core.sv changes at the edge)
    endtask
    task automatic hr(input [11:0] a, output [31:0] d);
        h_addr = a; h_re = 1'b1; @(posedge clk); #1; h_re = 1'b0; @(posedge clk); @(posedge clk); #1; d = h_rdata;
    endtask

    // ---------------------------------------------------------------- the synthetic feed
    logic        rxclk, txclk;
    assign txclk = u.txusr2; assign rxclk = u.rxusr2;
    logic [63:0] wmem [0:65535];
    integer      nw, widx, veto_arg, inst_arg, thr_arg, loop_n;
    string       fn;
    initial begin
        nw = 0; widx = 0; veto_arg = 0; inst_arg = 1; thr_arg = 9975; loop_n = 0;
        void'($value$plusargs("LOOP=%d", loop_n));        // +LOOP=<n>: no injection; the board's own stream, n generator feed frames (ADD ask 99.50, size 1, instrument 1) through the near-end loop
        if (loop_n == 0 && !$value$plusargs("WORDS=%s", fn)) begin $display("NO +WORDS"); $finish; end
        if (loop_n == 0 && !$value$plusargs("NW=%d", nw)) begin $display("NO +NW"); $finish; end
        void'($value$plusargs("VETO=%d", veto_arg));
        void'($value$plusargs("INST=%d", inst_arg));
        void'($value$plusargs("THR=%d", thr_arg));
        if (loop_n == 0) begin $readmemh(fn, wmem); u.u_gt.inj_en = 1'b1; end
    end
    always @(posedge rxclk) if (loop_n == 0) begin
        u.u_gt.inj_d <= (widx < nw) ? wmem[widx] : wmem[nw - 1];
        widx <= widx + 1;
    end

    // ---------------------------------------------------------------- the monitors (as tb_lat_core.sv)
    logic        x_v, y_v, m_v, fire, go_p, sop, rxsop_p;
    logic [7:0]  x_c, y_c;
    logic [63:0] x_d, y_d;
    logic [3:0]  td_wi;
    logic        td_feed, kind0;
    assign x_v = u.g_rm.u_rx.x_v; assign x_c = u.g_rm.u_rx.x_c; assign x_d = u.g_rm.u_rx.x_d;
    assign y_v = u.g_rm.u_rx.y_v; assign y_c = u.g_rm.u_rx.y_c; assign y_d = u.g_rm.u_rx.y_d;
    assign m_v = u.g_rm.u_rx.m_v; assign td_wi = u.g_rm.u_rx.u_td.wi; assign td_feed = u.g_rm.u_rx.u_td.is_feed; assign fire = u.g_rm.u_rx.u_td.fire;
    assign go_p = u.g_rm.u_tx.go_p; assign sop = u.g_rm.u_tx.sop; assign kind0 = (u.g_rm.u_tx.cur_kind == 0); assign rxsop_p = u.g_rm.u_tx.rx_sop_p;
    real t_x_start, t_x_price, t_y_price, t_w7, t_fire, t_go, t_sop, t_rxsop, quiet_until;
    int  nbx, nby, nord;
    logic have_x, have_y, have_w7, have_fire, have_go, have_rxsop;
    initial begin quiet_until = 0.0; nbx = -1; nby = -1; nord = 0; have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; t_x_start = 0; t_y_price = 0; t_rxsop = 0; end
    always @(posedge rxclk) begin
        real t;
        t = $realtime;
        #0.05;
        if (x_v && t > quiet_until) begin
            if ((x_c == 8'h01 && x_d[7:0] == 8'hFB) || (x_c == 8'h1F && x_d[39:32] == 8'hFB)) begin nbx = 0; t_x_start = t; have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; end
            else if (nbx >= 0) nbx = nbx + 1;
            if (nbx == 8 && !have_x) begin t_x_price = t; have_x = 1; end
        end
    end
    always @(posedge txclk) begin
        real t;
        t = $realtime;
        #0.05;
        if (y_v) begin
            if ((y_c == 8'h01 && y_d[7:0] == 8'hFB) || (y_c == 8'h1F && y_d[39:32] == 8'hFB)) nby = 0;
            else if (nby >= 0) nby = nby + 1;
            if (nby == 8 && have_x && !have_y) begin t_y_price = t; have_y = 1; end
        end
        if (have_x && !have_w7 && m_v && td_wi == 7 && td_feed) begin t_w7 = t; have_w7 = 1; end
        if (have_w7 && !have_fire && fire) begin t_fire = t; have_fire = 1; end
        if (nbx >= 0 && !have_rxsop && rxsop_p && t > t_x_start) begin t_rxsop = t; have_rxsop = 1; end
        if (have_fire && !have_go && go_p) begin t_go = t; have_go = 1; end
        if (have_go && sop && kind0) begin
            t_sop = t;
            $display("ORD %0d x_start %0.3f x_price %0.3f y_price %0.3f w7_mac %0.3f fire %0.3f go %0.3f sop_mac %0.3f rxsop %0.3f", nord, t_x_start, t_x_price, t_y_price, t_w7, t_fire, t_go, t_sop, t_rxsop);
            nord = nord + 1;
            have_x = 0; have_y = 0; have_w7 = 0; have_fire = 0; have_go = 0; have_rxsop = 0; nbx = -1; nby = -1;
            quiet_until = t + 150.0 * TREF;
        end
    end
    // per-message and per-decision lines, mid-clock (values of the clock in progress)
    int nmsg = 0, nfire = 0;
    always @(negedge txclk) begin
`ifdef ML
        if (u.g_rm.u_rx.u_td.ml_obs) begin
            $display("MSG %0d trk %b feat %h cls %0d ok %b agree %b hit %b dec %b veto %b type %0d side %b px %0d sz %0d", nmsg, u.g_rm.u_rx.u_td.ml_trk, u.g_rm.u_rx.u_td.u_ml.feat_r, u.g_rm.u_rx.u_td.u_ml.cls,
                     u.g_rm.u_rx.u_td.u_ml.cls_ok, u.g_rm.u_rx.u_td.ml_agree, u.g_rm.u_rx.u_td.hit, u.g_rm.u_rx.u_td.ml_dec, u.g_rm.u_rx.u_td.ml_veto, u.g_rm.u_rx.u_td.mtype,
                     u.g_rm.u_rx.u_td.side_ask, u.g_rm.u_rx.u_td.price, {u.g_rm.u_rx.u_td.m_d[23:16], u.g_rm.u_rx.u_td.m_d[31:24], u.g_rm.u_rx.u_td.m_d[39:32], u.g_rm.u_rx.u_td.m_d[47:40]});
            nmsg = nmsg + 1;
        end
`endif
        if (fire) begin $display("FIRE %0d", nfire); nfire = nfire + 1; end
    end

`ifdef DBG
    always @(posedge clk) if (h_we) begin #1; $display("DBG hw addr %h data %h rst %b snap7 %0d live7 %0d", h_addr, h_wdata, u.rst, u.rx_snap[32*7 +: 32], u.rx_live[32*7 +: 32]); end
`endif
    // ---------------------------------------------------------------- the run
    logic [31:0] st;
    task automatic show(input string name, input [11:0] a);
        logic [31:0] v;
        hr(a, v); $display("REG %s %0d", name, v);
    endtask
    initial begin
        repeat (6) @(posedge clk);
        rst = 1'b0;
        st = 0;
        for (int i = 0; i < 400 && !((st & 1) && (st & 2) && (st & 32'h200)); i++) begin
            #200; hr(12'h014, st);
        end
        if (!((st & 1) && (st & 2) && (st & 32'h200))) begin $display("LINK DID NOT COME UP: GTSTAT %h", st); $finish; end
        $display("LINK UP at %0t widx %0d", $time, widx);
        hw(12'h018, 1);
        hw(12'h060, thr_arg); hw(12'h064, 100);
        hw(12'h06C, (inst_arg << 16) | 66);
        hw(12'h068, 32'h1 | 32'h4 | ((loop_n > 0) ? (1 << 4) : 0));          // ARM, TRADE_EN, and for +LOOP the generator's feed kind
`ifdef ML
        hw(12'h304, inst_arg);
        hw(12'h300, veto_arg);
`endif
        // wait until the stream has been played (the first words are idles; the last ones are idles too), then read the counters
        if (loop_n > 0) begin
            hw(12'h070, 9950); hw(12'h074, 301); hw(12'h078, loop_n);
`ifdef ML
            hw(12'h300, 32'h2 | veto_arg);              // reset the stage's state and counters, as the board sequence does
`endif
            hw(12'h018, 2);
            #(real'(loop_n) * 301.0 * TREF + 20000.0);
        end else
        wait (widx >= nw - 560);                  // inside the tail of idle words (600), so the receiver stays locked while the counters are read
`ifdef ML
        $display("DIRECT n_frames %0d n_obs %0d n_apply %0d", u.g_rm.u_rx.u_td.n_frames, u.g_rm.u_rx.u_td.u_ml.n_obs, u.g_rm.u_rx.u_td.u_ml.n_apply);
`endif
`ifdef DBG
        $display("DBG pre rx_live7 %0d ml_live0 %0d t %0t", u.rx_live[32*7 +: 32], u.ml_live[31:0], $time);
`endif
        hw(12'h018, 4);
`ifdef DBG
        $display("DBG post-write rx_snap7 %0d p_snap %b t %0t", u.rx_snap[32*7 +: 32], u.p_snap, $time);
`endif
        #3000;
`ifdef DBG
        $display("DBG rx_live7 %0d rx_snap7 %0d ml_live0 %0d ml_snap0 %0d tx_live0 %0d", u.rx_live[32*7 +: 32], u.rx_snap[32*7 +: 32], u.ml_live[31:0], u.ml_snap[31:0], u.tx_live[31:0]);
`endif
        hr(12'h000, st); $display("ID %h", st);
        hr(12'h008, st); $display("FEATURES %h", st);
        hr(12'h014, st); $display("GTSTAT %h", st);
        show("tx_n_order", 12'h200 + 4 * 0); show("tx_poisoned", 12'h200 + 4 * 4); show("tx_dropped", 12'h200 + 4 * 5); show("tx_underrun", 12'h200 + 4 * 6);
        show("tx_late", 12'h200 + 4 * 7); show("tx_stale", 12'h200 + 4 * 8);
        show("rx_frames", 12'h100 + 4 * 7); show("rx_good", 12'h100 + 4 * 8); show("rx_bad", 12'h100 + 4 * 9); show("rx_err", 12'h100 + 4 * 10);
        show("rx_fired", 12'h100 + 4 * 11); show("rx_blocked", 12'h100 + 4 * 12); show("rx_toolong", 12'h100 + 4 * 13);
        show("rx_ovf", 12'h100 + 4 * 19); show("rx_ins", 12'h100 + 4 * 20); show("rx_del", 12'h100 + 4 * 21);
`ifdef ML
        for (int i = 0; i < 14; i++) begin hr(12'h310 + 4 * i, st); $display("MLV %0d %0d", i, st); end
        hr(12'h308, st); $display("ML_ID %h", st);
`endif
        $display("DONE orders %0d msgs %0d fires %0d", nord, nmsg, nfire);
        $finish;
    end
endmodule
