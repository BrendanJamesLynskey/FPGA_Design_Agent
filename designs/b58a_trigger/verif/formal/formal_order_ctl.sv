// formal_order_ctl.sv: the order slot of rtl/order_ctl.sv. Every input is free (frames, verdicts, rule firings, the
// interlocks' answers, kill, ARP requests); the MAC is an abstract one (a frame of L clocks, its last byte's FCS
// inverted if poison came before that byte). One order, chosen by the solver (watch), is followed by ghost logic
// that knows its frame's verdict independently of the slot's own bookkeeping.
module formal_order_ctl (
    input logic        clk,
    input logic        fire_v, fire_order, grant_in, frame_end_v, frame_good, frame_arp_req, kill_now, spec_en
);
    // the order's fields do not affect any property: held constant to keep the solver fast
    logic        o_side = 1'b0;
    logic [15:0] o_inst = 16'd0;
    logic [31:0] o_px = 32'd0, o_qty = 32'd0;
    localparam int WDOG = 8, L = 3;
    logic rst;
    logic f_past = 1'b0;
    logic [2:0] f_n = 3'd0;
    always_ff @(posedge clk) begin f_past <= 1'b1; if (f_n != 3'd7) f_n <= f_n + 3'd1; end
    assign rst = (f_n == 3'd0);
    (* anyconst *) logic [7:0] watch;
    always_comb assume (watch != 8'd0);
    always_ff @(posedge clk) if (f_past && !rst) assume (spec_en == $past(spec_en));

    // interlocks: an answer only to a request, one clock later
    logic req_v, req_q, grant, rej_v;
    always_ff @(posedge clk) req_q <= rst ? 1'b0 : req_v;
    assign grant = req_q && grant_in;
    assign rej_v = req_q && !grant_in;

    // abstract MAC
    logic tx_start, tx_ready, tx_last, tx_lp, tx_poison, m_busy, m_pz, m_gap;
    logic [1:0] m_cnt;
    assign tx_ready = !m_busy && !m_gap;
    assign tx_last  = m_busy && m_cnt == 2'd0;
    assign tx_lp    = m_pz;
    always_ff @(posedge clk) begin
        if (rst) begin m_busy <= 1'b0; m_cnt <= '0; m_pz <= 1'b0; m_gap <= 1'b0; end
        else begin
            m_gap <= 1'b0;
            if (!m_busy && !m_gap && tx_start) begin m_busy <= 1'b1; m_cnt <= 2'(L - 1); m_pz <= tx_poison; end
            else if (m_busy) begin
                if (m_cnt != 0) begin m_cnt <= m_cnt - 2'd1; if (tx_poison) m_pz <= 1'b1; end
                else begin m_busy <= 1'b0; m_gap <= 1'b1; end
            end
        end
    end

    logic [1:0] tx_kind;
    logic [31:0] cur_order_id;
    logic s_act, s_gnt, s_vk, s_vg, s_start, s_sent, cancel_pend;
    logic [7:0] s_gen, fgen;
    order_ctl #(.BUILD_MODE(0), .WDOG(WDOG)) dut (.clk, .rst, .soft_rst(1'b0), .spec_en, .kill_now,
        .my_mac(48'h0), .my_ip(32'h0), .my_port(16'h0), .dst_mac(48'h0), .dst_ip(32'h0), .dst_port(16'h0),
        .fire_v, .fire_order, .req_v, .grant, .rej_v, .o_side, .o_inst, .o_px, .o_qty,
        .frame_end_v, .frame_good, .frame_arp_req, .arp_sha(48'h0), .arp_spa(32'h0),
        .tx_start, .tx_len(), .tx_ready, .tx_req_valid(1'b0), .tx_req_idx(11'd0), .tx_data(), .tx_last_byte(),
        .tx_poison, .tx_last, .tx_last_poisoned(tx_lp), .tx_kind, .cur_order_id,
        .ev_suppress(), .ev_busy(), .ev_spec_drop(), .ev_spec_poison(), .ev_spec_cancel(), .ev_kill_drop(),
        .ev_order_sent(), .ev_cancel_sent(), .ev_arp_sent(), .ev_wdog(),
        .s_act, .s_gnt, .s_vk, .s_vg, .s_start, .s_sent, .s_gen, .fgen, .cancel_pend);

    // ---- ghost: the watched order and its own frame's verdict --------------------------------------------------------
    logic [7:0] w_next;                 // order ids handed out (one per grant answering a request)
    logic       g_req;                  // the request now with the interlocks would become the watched order
    logic       g_mine, g_vk, g_bad, g_started, g_sent, g_clean, g_cancel;
    logic [7:0] g_wait;                 // clocks since a clean send of a bad-frame order without a cancel
    logic [15:0] g_age;                 // clocks since the request (the watchdog treats no verdict by WDOG as bad)
    always_ff @(posedge clk) begin
        if (rst) begin
            w_next <= 8'd1; g_req <= 1'b0; g_mine <= 1'b0; g_vk <= 1'b0; g_bad <= 1'b0; g_started <= 1'b0;
            g_sent <= 1'b0; g_clean <= 1'b0; g_cancel <= 1'b0; g_wait <= '0; g_age <= '0;
        end else begin
            // a request: if it is granted it gets id w_next; its frame's verdict is the first one from this clock on
            if (req_v) begin g_req <= (w_next == watch); end
            if (req_v && w_next == watch && !g_mine) begin
                g_vk <= frame_end_v; g_bad <= frame_end_v && !frame_good; g_age <= '0;
            end else if ((g_req || g_mine) && !g_vk) begin
                if (frame_end_v) begin g_vk <= 1'b1; g_bad <= !frame_good; end
                else if (g_age >= 16'(WDOG)) begin g_vk <= 1'b1; g_bad <= 1'b1; end    // the watchdog's verdict
                g_age <= g_age + 16'd1;
            end
            if (grant) begin
                w_next <= w_next + 8'd1;
                if (g_req) g_mine <= 1'b1;
            end
            if (rej_v && g_req) begin g_req <= 1'b0; g_vk <= 1'b0; end
            // the watched order on the wire
            if (tx_kind == 2'd1 && cur_order_id[7:0] == watch && g_mine) begin
                if (!g_started) g_started <= 1'b1;
                if (tx_last) begin g_sent <= 1'b1; g_clean <= !tx_lp; end
            end
            if (tx_kind == 2'd2 && cur_order_id[7:0] == watch && g_mine) g_cancel <= 1'b1;
            if (g_vk && g_bad && g_sent && g_clean && !g_cancel) g_wait <= g_wait + 8'd1;
        end
    end
    logic g_bad_now;
    assign g_bad_now = g_vk && g_bad;

    // ---- properties --------------------------------------------------------------------------------------------------
    logic [7:0] act_run;                // consecutive clocks the slot has been busy
    always_ff @(posedge clk) act_run <= (rst || !s_act) ? 8'd0 : act_run + 8'd1;
    always_ff @(posedge clk) if (f_past && !rst && !$past(rst)) begin
        // B1: an order whose frame was bad is never started once that is known (the start decision is the clock
        // before the order shows on tx_kind; a verdict arriving in that clock is already in g_bad_now here) ...
        if (tx_kind == 2'd1 && cur_order_id[7:0] == watch && g_mine && !g_started) assert (!g_bad_now);
        // ... and if it left with a good FCS, a cancel for it starts within 12 clocks (two 3-clock frames and gaps)
        assert (g_wait <= 8'd12);
        // a cancel only ever follows a bad frame (or no verdict within the watchdog's time)
        if (g_cancel) assert (g_vk && g_bad);
        // safe mode: an order never starts before its frame is known good
        if (!spec_en && g_started) assert (g_vk && !g_bad);
        // B2: the slot always drains (watchdog WDOG, then at most a frame, a cancel and their gaps on the wire)
        assert (act_run <= 8'(WDOG + 16));
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        cover (g_sent && g_bad && !g_clean);            // poisoned on the wire
        cover (g_cancel);                                // cancelled after a clean send
        cover (g_mine && g_bad && !g_started && !s_act); // dropped before it started
        cover (act_run == 8'(WDOG + 2));                 // the watchdog's reach
    end
endmodule
