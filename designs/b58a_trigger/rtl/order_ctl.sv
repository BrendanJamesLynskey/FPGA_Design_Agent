// order_ctl.sv: what leaves the trading port: orders, speculative undo, cancels and ARP replies (brief 58A steps 2, 4).
//
// One order slot, tied to the frame whose message triggered it:
//   speculative mode (spec_en = 1): the order is queued at once and goes out while the trigger frame is still
//   arriving. When that frame's verdict comes (frame_end_v):
//     good             nothing to do
//     bad, still queued        dropped (ev_spec_drop)
//     bad, being transmitted   its FCS is poisoned, so the far end discards it (ev_spec_poison)
//     bad, already sent        a CANCEL_ORDER for its order id is sent (ev_spec_cancel)
//   safe mode (spec_en = 0): the order is held until the verdict and sent only on a good frame.
// At most one order per received frame: further requests in the same frame are refused before the interlocks
// (ev_suppress), and so are requests while the slot is still busy with an earlier order (ev_busy). kill drops a
// queued or held order that has not started (ev_kill_drop); a frame already on the wire finishes.
// Priority on the wire: cancel, then order, then ARP reply.
//
// Response frames (docs/bench_feed_v1.md "Orders"): Ethernet II, IPv4 (no options, DF, TTL 64, identification 0,
// header checksum from the template), UDP (checksum 0), and a one-message Bench Feed v1 packet.
// BUILD_MODE 0 (pre-built): the headers are a function of the template registers only, ready before any decision,
// and the MAC starts the clock after the grant; each byte is produced as the MAC asks for it. BUILD_MODE 1
// (assemble then send, for comparison): after the grant the whole frame is first written into a buffer, one byte a
// clock, and only then sent. The cycle difference is measured in tests/test_b58a_rtl.py.

module order_ctl #(
    parameter int BUILD_MODE = 0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        spec_en,
    input  logic        kill_now,
    input  logic [47:0] my_mac,
    input  logic [31:0] my_ip,
    input  logic [15:0] my_port,
    input  logic [47:0] dst_mac,
    input  logic [31:0] dst_ip,
    input  logic [15:0] dst_port,
    // requests from the rules (before the interlocks)
    input  logic        fire_v,
    input  logic        fire_order,
    output logic        req_v,          // to the interlocks
    input  logic        grant,
    input  logic        rej_v,
    input  logic        o_side,
    input  logic [15:0] o_inst,
    input  logic [31:0] o_px,
    input  logic [31:0] o_qty,
    // trigger frame verdicts and ARP
    input  logic        frame_end_v,
    input  logic        frame_good,
    input  logic        frame_arp_req,
    input  logic [47:0] arp_sha,
    input  logic [31:0] arp_spa,
    // to mac_tx
    output logic        tx_start,
    output logic [10:0] tx_len,
    input  logic        tx_ready,
    input  logic        tx_req_valid,
    input  logic [10:0] tx_req_idx,
    output logic [7:0]  tx_data,
    output logic        tx_last_byte,   // tx_data is the frame's last byte
    output logic        tx_poison,
    input  logic        tx_last,        // mac_tx last_pulse
    output logic [1:0]  tx_kind,        // the frame being sent: 1 order, 2 cancel, 3 ARP reply
    output logic [31:0] cur_order_id,   // the order id of the frame being sent
    // events
    output logic        ev_suppress,
    output logic        ev_busy,
    output logic        ev_spec_drop,
    output logic        ev_spec_poison,
    output logic        ev_spec_cancel,
    output logic        ev_kill_drop,
    output logic        ev_order_sent,  // an order frame started (first preamble byte next clock)
    output logic        ev_cancel_sent,
    output logic        ev_arp_sent
);
    localparam logic [2:0] P_NONE = 3'd0, P_HELD = 3'd1, P_QUEUED = 3'd2, P_INFLIGHT = 3'd3, P_DONE = 3'd4,
                           P_SENDING = 3'd5;    // a confirmed order still being sent (its frame is settled)
    localparam logic [1:0] K_NONE = 2'd0, K_ORDER = 2'd1, K_CANCEL = 2'd2, K_ARP = 2'd3;
    localparam logic [10:0] LEN_ORDER = 11'd66, LEN_ARP = 11'd42;

    logic [2:0]  ps;
    logic        this_frame;            // the slot's order came from the frame now arriving
    logic        ordered_in_frame;      // an order request was already made in the frame now arriving
    logic        o_s;
    logic [15:0] o_i;
    logic [31:0] o_p, o_q, o_id, next_id, out_seq;
    logic        cancel_pend;
    logic [31:0] c_id;
    logic        c_s;
    logic [15:0] c_i;
    logic [31:0] c_p, c_q;
    logic        arp_pend;
    logic [47:0] a_sha;
    logic [31:0] a_spa;
    logic        poison_q;
    logic        req_wait;              // a request is with the interlocks (answer next clock)

    // ---- request gate ---------------------------------------------------------------------------------------
    logic slot_free;
    assign slot_free = (ps == P_NONE) && !req_wait;
    assign req_v = fire_v && fire_order && !ordered_in_frame && slot_free;

    // ---- the IPv4 header checksum of the response template (pre-built: depends on registers only) ---------------
    function automatic logic [15:0] ip_csum(input logic [31:0] sip, input logic [31:0] dip, input logic [15:0] tlen);
        logic [31:0] s;
        s = 32'h4500 + {16'h0, tlen} + 32'h0000 + 32'h4000 + 32'h4011
            + {16'h0, sip[31:16]} + {16'h0, sip[15:0]} + {16'h0, dip[31:16]} + {16'h0, dip[15:0]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        return ~s[15:0];
    endfunction
    logic [15:0] csum_q;
    always_ff @(posedge clk) csum_q <= ip_csum(my_ip, dst_ip, 16'd52);

    // ---- frame bytes ------------------------------------------------------------------------------------------
    logic [1:0]  kind;                  // frame selected for the MAC
    logic [31:0] f_id, f_seq, f_p, f_q;
    logic        f_s;
    logic [15:0] f_i;
    logic        f_cancel;
    function automatic logic [7:0] b32(input logic [31:0] v, input logic [1:0] k);
        case (k)
            2'd0: return v[31:24];
            2'd1: return v[23:16];
            2'd2: return v[15:8];
            default: return v[7:0];
        endcase
    endfunction
    function automatic logic [7:0] b48(input logic [47:0] v, input logic [2:0] k);
        case (k)
            3'd0: return v[47:40];
            3'd1: return v[39:32];
            3'd2: return v[31:24];
            3'd3: return v[23:16];
            3'd4: return v[15:8];
            default: return v[7:0];
        endcase
    endfunction
    logic [7:0] fb;
    logic [10:0] fi;                    // the index whose byte fb is
    always_comb begin
        fb = 8'h00;
        if (kind == K_ARP) begin
            if (fi <= 11'd5)       fb = b48(a_sha, 3'(fi));
            else if (fi <= 11'd11) fb = b48(my_mac, 3'(fi - 11'd6));
            else case (fi)
                11'd12: fb = 8'h08; 11'd13: fb = 8'h06;
                11'd14: fb = 8'h00; 11'd15: fb = 8'h01; 11'd16: fb = 8'h08; 11'd17: fb = 8'h00;
                11'd18: fb = 8'h06; 11'd19: fb = 8'h04; 11'd20: fb = 8'h00; 11'd21: fb = 8'h02;
                default: begin
                    if (fi >= 11'd22 && fi <= 11'd27)      fb = b48(my_mac, 3'(fi - 11'd22));
                    else if (fi >= 11'd28 && fi <= 11'd31) fb = b32(my_ip, 2'(fi - 11'd28));
                    else if (fi >= 11'd32 && fi <= 11'd37) fb = b48(a_sha, 3'(fi - 11'd32));
                    else if (fi >= 11'd38 && fi <= 11'd41) fb = b32(a_spa, 2'(fi - 11'd38));
                end
            endcase
        end else begin
            if (fi <= 11'd5)       fb = b48(dst_mac, 3'(fi));
            else if (fi <= 11'd11) fb = b48(my_mac, 3'(fi - 11'd6));
            else case (fi)
                11'd12: fb = 8'h08; 11'd13: fb = 8'h00;
                11'd14: fb = 8'h45; 11'd15: fb = 8'h00; 11'd16: fb = 8'h00; 11'd17: fb = 8'd52;
                11'd18: fb = 8'h00; 11'd19: fb = 8'h00; 11'd20: fb = 8'h40; 11'd21: fb = 8'h00;
                11'd22: fb = 8'd64; 11'd23: fb = 8'd17; 11'd24: fb = csum_q[15:8]; 11'd25: fb = csum_q[7:0];
                11'd34: fb = my_port[15:8];  11'd35: fb = my_port[7:0];
                11'd36: fb = dst_port[15:8]; 11'd37: fb = dst_port[7:0];
                11'd38: fb = 8'h00; 11'd39: fb = 8'd32; 11'd40: fb = 8'h00; 11'd41: fb = 8'h00;
                11'd42: fb = 8'h42; 11'd43: fb = 8'h46; 11'd44: fb = 8'h01; 11'd45: fb = 8'h01;
                11'd50: fb = f_cancel ? 8'h11 : 8'h10;
                11'd51: fb = {7'd0, f_s};
                11'd52: fb = f_i[15:8]; 11'd53: fb = f_i[7:0];
                default: begin
                    if (fi >= 11'd26 && fi <= 11'd29)      fb = b32(my_ip, 2'(fi - 11'd26));
                    else if (fi >= 11'd30 && fi <= 11'd33) fb = b32(dst_ip, 2'(fi - 11'd30));
                    else if (fi >= 11'd46 && fi <= 11'd49) fb = b32(f_seq, 2'(fi - 11'd46));
                    else if (fi >= 11'd54 && fi <= 11'd57) fb = b32(f_p, 2'(fi - 11'd54));
                    else if (fi >= 11'd58 && fi <= 11'd61) fb = b32(f_q, 2'(fi - 11'd58));
                    else if (fi >= 11'd62 && fi <= 11'd65) fb = b32(f_id, 2'(fi - 11'd62));
                end
            endcase
        end
    end

    // ---- assemble-then-send buffer (BUILD_MODE 1 only) ---------------------------------------------------------
    logic [7:0]  abuf [128];
    logic        asm_busy;
    logic [10:0] asm_i;
    logic        asm_done;
    assign fi = (BUILD_MODE == 1 && asm_busy) ? asm_i : tx_req_idx;
    always_ff @(posedge clk) begin
        if (BUILD_MODE == 1) begin
            if (asm_busy) abuf[asm_i[6:0]] <= fb;
            tx_data <= abuf[tx_req_idx[6:0]];
        end else begin
            tx_data <= fb;
        end
        tx_last_byte <= (tx_req_idx + 11'd1 == tx_len);
    end

    // ---- slot, cancel, ARP and the MAC --------------------------------------------------------------------------
    logic sending;                      // a frame of ours is between start and last byte
    logic [2:0] ps_tx;                  // the slot state after this clock's last byte, if any
    assign ps_tx = (tx_last && sending && kind == K_ORDER && ps == P_INFLIGHT) ? P_DONE :
                   (tx_last && sending && kind == K_ORDER && ps == P_SENDING)  ? P_NONE : ps;
    logic bad_now;                      // the trigger frame turned out bad in this clock, its order on the wire
    assign bad_now = frame_end_v && !frame_good && this_frame && ps == P_INFLIGHT && !tx_last;
    always_ff @(posedge clk) begin
        ev_suppress <= 1'b0; ev_busy <= 1'b0; ev_spec_drop <= 1'b0; ev_spec_poison <= 1'b0; ev_spec_cancel <= 1'b0;
        ev_kill_drop <= 1'b0; ev_order_sent <= 1'b0; ev_cancel_sent <= 1'b0; ev_arp_sent <= 1'b0;
        tx_start <= 1'b0;
        if (rst) begin
            ps <= P_NONE; this_frame <= 1'b0; ordered_in_frame <= 1'b0; req_wait <= 1'b0;
            o_s <= 1'b0; o_i <= '0; o_p <= '0; o_q <= '0; o_id <= '0; next_id <= 32'd1; out_seq <= 32'd1;
            cancel_pend <= 1'b0; c_id <= '0; c_s <= 1'b0; c_i <= '0; c_p <= '0; c_q <= '0;
            arp_pend <= 1'b0; a_sha <= '0; a_spa <= '0; poison_q <= 1'b0;
            kind <= K_NONE; f_id <= '0; f_seq <= '0; f_p <= '0; f_q <= '0; f_s <= 1'b0; f_i <= '0; f_cancel <= 1'b0;
            tx_len <= '0; sending <= 1'b0; asm_busy <= 1'b0; asm_i <= '0; asm_done <= 1'b0;
            cur_order_id <= '0;
        end else begin
            // requests
            if (fire_v && fire_order) begin
                if (ordered_in_frame)  ev_suppress <= 1'b1;
                else if (!slot_free)   ev_busy <= 1'b1;
            end
            if (req_v) begin req_wait <= 1'b1; ordered_in_frame <= 1'b1; end
            if (req_wait) req_wait <= 1'b0;
            if (grant) begin
                ps <= spec_en ? P_QUEUED : P_HELD; this_frame <= 1'b1;
                o_s <= o_side; o_i <= o_inst; o_p <= o_px; o_q <= o_qty; o_id <= next_id;
                next_id <= next_id + 32'd1;
            end
            // kill: a queued or held order that has not started is dropped
            if (kill_now && (ps == P_QUEUED || ps == P_HELD) && !(grant)) begin
                ps <= P_NONE; ev_kill_drop <= 1'b1;
            end
            // the trigger frame's verdict
            // the frame's end (before the verdict, which then sees P_DONE when both come in one clock)
            if (tx_last && sending) begin
                sending <= 1'b0; poison_q <= 1'b0;
                if (kind == K_ORDER) begin
                    if (ps == P_INFLIGHT) ps <= P_DONE;
                    else if (ps == P_SENDING) ps <= P_NONE;
                end
            end
            if (frame_end_v) begin
                ordered_in_frame <= 1'b0;
                this_frame <= 1'b0;
                if (this_frame) begin
                    if (frame_good) begin
                        case (ps_tx)
                            P_HELD:     ps <= kill_now ? P_NONE : P_QUEUED;
                            P_DONE:     ps <= P_NONE;
                            P_INFLIGHT: ps <= P_SENDING;
                            default: ;
                        endcase
                    end else begin
                        case (ps_tx)
                            P_HELD, P_QUEUED: begin ps <= P_NONE; ev_spec_drop <= 1'b1; end
                            P_INFLIGHT: begin ps <= P_SENDING; poison_q <= 1'b1; ev_spec_poison <= 1'b1; end
                            P_SENDING:  ;
                            P_DONE: begin
                                ps <= P_NONE; ev_spec_cancel <= 1'b1;
                                cancel_pend <= 1'b1; c_id <= o_id; c_s <= o_s; c_i <= o_i; c_p <= o_p; c_q <= o_q;
                            end
                            default: ;
                        endcase
                    end
                end
                if (frame_good && frame_arp_req) begin arp_pend <= 1'b1; a_sha <= arp_sha; a_spa <= arp_spa; end
            end
            // choose and start the next frame
            if (!sending && !asm_busy && !asm_done && tx_ready && !tx_start) begin
                if (cancel_pend) begin
                    kind <= K_CANCEL; f_cancel <= 1'b1; f_id <= c_id; f_s <= c_s; f_i <= c_i; f_p <= c_p; f_q <= c_q;
                    f_seq <= out_seq; out_seq <= out_seq + 32'd1; cancel_pend <= 1'b0; tx_len <= LEN_ORDER;
                    cur_order_id <= c_id; ev_cancel_sent <= 1'b1;
                    if (BUILD_MODE == 1) begin asm_busy <= 1'b1; asm_i <= '0; end else begin tx_start <= 1'b1; sending <= 1'b1; end
                end else if (ps == P_QUEUED && !kill_now) begin
                    kind <= K_ORDER; f_cancel <= 1'b0; f_id <= o_id; f_s <= o_s; f_i <= o_i; f_p <= o_p; f_q <= o_q;
                    f_seq <= out_seq; out_seq <= out_seq + 32'd1; tx_len <= LEN_ORDER;
                    cur_order_id <= o_id; ev_order_sent <= 1'b1;
                    ps <= this_frame ? P_INFLIGHT : P_SENDING;
                    if (BUILD_MODE == 1) begin asm_busy <= 1'b1; asm_i <= '0; end else begin tx_start <= 1'b1; sending <= 1'b1; end
                end else if (arp_pend) begin
                    kind <= K_ARP; arp_pend <= 1'b0; tx_len <= LEN_ARP; ev_arp_sent <= 1'b1;
                    if (BUILD_MODE == 1) begin asm_busy <= 1'b1; asm_i <= '0; end else begin tx_start <= 1'b1; sending <= 1'b1; end
                end
            end
            // assemble-then-send: write the frame, then start
            if (asm_busy) begin
                asm_i <= asm_i + 11'd1;
                if (asm_i + 11'd1 == tx_len) begin asm_busy <= 1'b0; asm_done <= 1'b1; end
            end
            if (asm_done) begin asm_done <= 1'b0; tx_start <= 1'b1; sending <= 1'b1; end
        end
    end
    assign tx_kind   = sending ? kind : K_NONE;
    assign tx_poison = (poison_q || bad_now) && sending && kind == K_ORDER;
endmodule
