// order_ctl.sv: what leaves the trading port: orders, the undo of speculative orders, cancels and ARP replies.
//
// Frames and verdicts. Every received frame ends with one verdict (frame_end_v, frame_good). fgen counts verdicts,
// so the frame now arriving is generation fgen. An order request (req_v) is tied to the generation of the frame whose
// message triggered it, and that frame's verdict is recorded in the order slot whenever it arrives: before the
// request is answered, in the same clock as the grant or the start, while the order is on the wire, or after it has
// left. The slot is a set of independent flags (granted, verdict known and good, started, sent, sent clean), each
// written in one place, so two events in one clock cannot overwrite each other.
//
// An order whose frame turns out bad is always undone:
//   not yet started                 dropped, in either mode (ev_spec_drop)
//   on the wire                     its remaining FCS bytes are inverted (poison), so the far end discards it
//   already sent with a good FCS    a CANCEL_ORDER for its id is sent (ev_spec_cancel)
// Speculative mode (spec_en = 1) starts the order as soon as it is granted and its frame is not known bad; safe mode
// starts it only after its frame is known good. Properties: verif/formal/formal_order_ctl.sv.
//
// The slot always drains: if the verdict has not arrived WDOG clocks after the request (a lost end token, for example),
// the frame is treated as bad (ev_wdog), which drops, poisons or cancels the order as above. soft_rst (a register
// pulse) drops an order that has not started and a pending ARP reply, and forgets which frame last asked; it never
// removes an undo: an order already started still waits for its verdict (or the watchdog) and is poisoned or
// cancelled if its frame was bad, a pending cancel is still sent, and a frame being assembled or sent finishes.
// The request record of a frame is cleared at that frame's verdict, so the frame counter's wrap cannot suppress a
// later frame's request. GEN_W (the frame counter's width) is 8; the formal harness narrows it to reach the wrap.
// One order slot: at most one order request per received frame (ev_suppress) and none while the slot is busy
// (ev_busy). kill drops a granted order that has not started (ev_kill_drop). Priority on the wire: cancel, order,
// ARP reply.
//
// Response frames (docs/bench_feed_v1.md "Orders"): Ethernet II, IPv4 (DF, TTL 64, identification = the frame's
// sequence number, header checksum), UDP (checksum 0), one Bench Feed v1 message.
// BUILD_MODE 0: the IPv4 checksum of the next response is computed before any decision; bytes are produced as the MAC
//   asks for them.
// BUILD_MODE 1: the checksum is computed after the start, one header word a clock, while the preamble and the first
//   header bytes go out; bytes are produced as the MAC asks for them (the fair comparison for "pre-built headers").
// BUILD_MODE 2: store and assemble: after the decision the whole frame is written to a buffer, one byte a clock, and
//   only then sent.

module order_ctl #(
    parameter int BUILD_MODE = 0,
    parameter int WDOG       = 4096,    // clocks from request to verdict before the frame is treated as bad
    parameter int GEN_W      = 8        // width of the frame counter (fgen, s_gen)
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        soft_rst,
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
    output logic        req_v,
    input  logic        grant,
    input  logic        rej_v,
    input  logic        o_side,
    input  logic [15:0] o_inst,
    input  logic [31:0] o_px,
    input  logic [31:0] o_qty,
    // received frames' verdicts and ARP
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
    output logic        tx_last_byte,
    output logic        tx_poison,
    input  logic        tx_last,
    input  logic        tx_last_poisoned,
    output logic [1:0]  tx_kind,        // the frame being sent: 1 order, 2 cancel, 3 ARP reply
    output logic [31:0] cur_order_id,
    // events
    output logic        ev_suppress,
    output logic        ev_busy,
    output logic        ev_spec_drop,
    output logic        ev_spec_poison,
    output logic        ev_spec_cancel,
    output logic        ev_kill_drop,
    output logic        ev_order_sent,
    output logic        ev_cancel_sent,
    output logic        ev_arp_sent,
    output logic        ev_wdog,
    // state, for the formal properties and the register map
    output logic        s_act,
    output logic        s_gnt,
    output logic        s_vk,
    output logic        s_vg,
    output logic        s_start,
    output logic        s_sent,
    output logic [GEN_W-1:0] s_gen,
    output logic [GEN_W-1:0] fgen,
    output logic        cancel_pend
);
    initial begin
        if (BUILD_MODE < 0 || BUILD_MODE > 2) $error("order_ctl: BUILD_MODE must be 0, 1 or 2 (got %0d)", BUILD_MODE);
        if (WDOG < 8 || WDOG > 65535) $error("order_ctl: WDOG must be in 8..65535 (got %0d)", WDOG);
    end
    localparam logic [1:0] K_NONE = 2'd0, K_ORDER = 2'd1, K_CANCEL = 2'd2, K_ARP = 2'd3;
    localparam logic [10:0] LEN_ORDER = 11'd66, LEN_ARP = 11'd42;

    // ---- the slot ------------------------------------------------------------------------------------------------
    logic        s_wait;                // the request is with the interlocks; the answer comes this clock
    logic        s_clean;               // sent with a good FCS
    logic [15:0] s_age;
    logic        o_s;
    logic [15:0] o_i;
    logic [31:0] o_p, o_q, o_id, next_id, out_seq;
    logic        rq_valid;              // a request was made in frame generation rq_gen
    logic [GEN_W-1:0] rq_gen;
    logic        c_s;
    logic [15:0] c_i;
    logic [31:0] c_p, c_q, c_id;
    logic        arp_pend;
    logic [47:0] a_sha;
    logic [31:0] a_spa;
    logic        sending;
    logic [1:0]  kind;

    // the slot frame's verdict, including one arriving in this clock
    logic v_now, wd_now, vk_e, vg_e, bad_e, good_e;
    assign v_now  = frame_end_v && s_act && !s_vk && (s_gen == fgen);
    assign wd_now = s_act && !s_vk && !v_now && (s_age >= 16'(WDOG));   // the watchdog's verdict: bad
    assign vk_e   = s_vk || v_now || wd_now;
    assign vg_e   = s_vk ? s_vg : (v_now && frame_good);
    assign bad_e  = vk_e && !vg_e;
    assign good_e = vk_e && vg_e;

    // requests: one per frame, none while the slot is busy
    logic in_frame_done;
    assign in_frame_done = rq_valid && (rq_gen == fgen);
    assign req_v = fire_v && fire_order && !in_frame_done && !s_act && !soft_rst;

    // the order's transmission
    logic order_tx, order_last;
    assign order_tx   = sending && kind == K_ORDER;
    assign order_last = order_tx && tx_last;
    logic sent_e, clean_e;                // sent (including this clock's last byte), and whether cleanly
    assign sent_e  = s_sent || order_last;
    assign clean_e = s_sent ? s_clean : !tx_last_poisoned;

    // start rule for the slot's order
    logic order_ok;
    assign order_ok = s_act && s_gnt && !s_wait && !s_start && !kill_now && (spec_en ? !bad_e : good_e);

    // the slot completes when the order has been dropped, or sent with its verdict known
    logic drop_bad, drop_kill, done_sent, need_cancel;
    assign drop_bad    = s_act && !s_wait && !s_start && bad_e;
    assign drop_kill   = s_act && !s_wait && s_gnt && !s_start && kill_now && !bad_e;
    assign done_sent   = s_act && sent_e && vk_e;
    assign need_cancel = done_sent && bad_e && clean_e;

    // ---- the IPv4 header checksum ---------------------------------------------------------------------------------
    function automatic logic [15:0] ip_csum(input logic [31:0] sip, input logic [31:0] dip, input logic [15:0] ident);
        logic [31:0] s;
        s = 32'h4500 + 32'd52 + {16'h0, ident} + 32'h4000 + 32'h4011
            + {16'h0, sip[31:16]} + {16'h0, sip[15:0]} + {16'h0, dip[31:16]} + {16'h0, dip[15:0]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        ip_csum = ~s[15:0];
    endfunction
    logic [15:0] csum_next;              // BUILD_MODE 0 and 2: for the next frame's sequence number, before any decision
    always_ff @(posedge clk) csum_next <= ip_csum(my_ip, dst_ip, out_seq[15:0]);
    logic [15:0] f_csum;
    logic [31:0] cs_acc;                 // BUILD_MODE 1: the sum, one header word a clock
    logic [3:0]  cs_i;

    // ---- frame bytes ------------------------------------------------------------------------------------------------
    logic [31:0] f_id, f_seq, f_p, f_q;
    logic        f_s, f_cancel;
    logic [15:0] f_i;
    function automatic logic [7:0] b32(input logic [31:0] v, input logic [1:0] k);
        case (k)
            2'd0: b32 = v[31:24];
            2'd1: b32 = v[23:16];
            2'd2: b32 = v[15:8];
            default: b32 = v[7:0];
        endcase
    endfunction
    function automatic logic [7:0] b48(input logic [47:0] v, input logic [2:0] k);
        case (k)
            3'd0: b48 = v[47:40];
            3'd1: b48 = v[39:32];
            3'd2: b48 = v[31:24];
            3'd3: b48 = v[23:16];
            3'd4: b48 = v[15:8];
            default: b48 = v[7:0];
        endcase
    endfunction
    logic [7:0]  fb;
    logic [10:0] fi;
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
                11'd18: fb = f_seq[15:8]; 11'd19: fb = f_seq[7:0]; 11'd20: fb = 8'h40; 11'd21: fb = 8'h00;
                11'd22: fb = 8'd64; 11'd23: fb = 8'd17; 11'd24: fb = f_csum[15:8]; 11'd25: fb = f_csum[7:0];
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

    // ---- store and assemble (BUILD_MODE 2) -----------------------------------------------------------------------------
    logic [7:0]  abuf [128];
    logic        asm_busy, asm_done;
    logic [10:0] asm_i;
    assign fi = (BUILD_MODE == 2 && asm_busy) ? asm_i : tx_req_idx;
    always_ff @(posedge clk) begin
        if (BUILD_MODE == 2) begin
            if (asm_busy) abuf[asm_i[6:0]] <= fb;
            tx_data <= abuf[tx_req_idx[6:0]];
        end else begin
            tx_data <= fb;
        end
        tx_last_byte <= (tx_req_idx + 11'd1 == tx_len);
    end

    // ---- choose the next frame ------------------------------------------------------------------------------------------
    logic can_start, start_cancel, start_order, start_arp;
    assign can_start    = !sending && !asm_busy && !asm_done && tx_ready && !tx_start;
    assign start_cancel = can_start && cancel_pend;                         // an undo: a soft reset never holds it
    assign start_order  = can_start && !cancel_pend && order_ok && !soft_rst;
    assign start_arp    = can_start && !cancel_pend && !order_ok && arp_pend && !soft_rst;

    // ---- registers ------------------------------------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        ev_suppress <= 1'b0; ev_busy <= 1'b0; ev_spec_drop <= 1'b0; ev_spec_poison <= 1'b0; ev_spec_cancel <= 1'b0;
        ev_kill_drop <= 1'b0; ev_order_sent <= 1'b0; ev_cancel_sent <= 1'b0; ev_arp_sent <= 1'b0; ev_wdog <= 1'b0;
        tx_start <= 1'b0;
        if (rst) begin
            s_act <= 1'b0; s_wait <= 1'b0; s_gnt <= 1'b0; s_vk <= 1'b0; s_vg <= 1'b0; s_start <= 1'b0; s_sent <= 1'b0;
            s_clean <= 1'b0; s_age <= '0; s_gen <= '0;
            rq_valid <= 1'b0; rq_gen <= '0; cancel_pend <= 1'b0; arp_pend <= 1'b0;
            asm_busy <= 1'b0; asm_done <= 1'b0; asm_i <= '0;
            fgen <= '0; next_id <= 32'd1; out_seq <= 32'd1; sending <= 1'b0; kind <= K_NONE;
            o_s <= 1'b0; o_i <= '0; o_p <= '0; o_q <= '0; o_id <= '0; c_s <= 1'b0; c_i <= '0; c_p <= '0; c_q <= '0;
            c_id <= '0; a_sha <= '0; a_spa <= '0; f_id <= '0; f_seq <= '0; f_p <= '0; f_q <= '0; f_s <= 1'b0;
            f_i <= '0; f_cancel <= 1'b0; f_csum <= '0; cs_acc <= '0; cs_i <= '0; tx_len <= '0; cur_order_id <= '0;
        end else begin
            if (frame_end_v) fgen <= fgen + 1'b1;
            // ---- requests
            if (fire_v && fire_order) begin
                if (in_frame_done) ev_suppress <= 1'b1;
                else if (s_act)    ev_busy <= 1'b1;
            end
            if (req_v) begin
                s_act <= 1'b1; s_wait <= 1'b1; s_gnt <= 1'b0; s_start <= 1'b0; s_sent <= 1'b0; s_clean <= 1'b0;
                s_age <= '0; s_gen <= fgen;
                s_vk <= frame_end_v; s_vg <= frame_good;    // the frame's verdict may arrive in the request clock
                rq_valid <= !frame_end_v; rq_gen <= fgen;    // its verdict in this clock ends the record at once
                o_s <= o_side; o_i <= o_inst; o_p <= o_px; o_q <= o_qty;
            end else begin
                if (frame_end_v && rq_gen == fgen) rq_valid <= 1'b0;    // the requesting frame's verdict
            end
            if (!req_v && s_act) begin
                if (v_now) begin s_vk <= 1'b1; s_vg <= frame_good; end
                if (s_age != 16'hFFFF) s_age <= s_age + 16'd1;
                if (wd_now) begin s_vk <= 1'b1; s_vg <= 1'b0; ev_wdog <= 1'b1; end
                // the interlocks' answer
                if (s_wait) begin
                    s_wait <= 1'b0;
                    if (grant) begin s_gnt <= 1'b1; o_id <= next_id; next_id <= next_id + 32'd1; end
                    else s_act <= 1'b0;                    // refused (or killed in the grant clock)
                end
                // completion (each case clears the slot; a needed cancel waits for the cancel buffer)
                if (drop_bad) begin
                    s_act <= 1'b0; if (s_gnt) ev_spec_drop <= 1'b1;
                end else if (drop_kill) begin
                    s_act <= 1'b0; ev_kill_drop <= 1'b1;
                end else if (done_sent) begin
                    if (!need_cancel) begin
                        s_act <= 1'b0;
                        if (bad_e) ev_spec_poison <= 1'b1;
                    end else if (!cancel_pend || start_cancel) begin
                        s_act <= 1'b0; ev_spec_cancel <= 1'b1;
                        cancel_pend <= 1'b1; c_id <= o_id; c_s <= o_s; c_i <= o_i; c_p <= o_p; c_q <= o_q;
                    end
                end
            end
            if (order_last) begin s_sent <= 1'b1; s_clean <= !tx_last_poisoned; end
            if (frame_end_v && frame_good && frame_arp_req) begin arp_pend <= 1'b1; a_sha <= arp_sha; a_spa <= arp_spa; end
            // ---- the next frame
            if (start_cancel) begin
                kind <= K_CANCEL; f_cancel <= 1'b1; f_id <= c_id; f_s <= c_s; f_i <= c_i; f_p <= c_p; f_q <= c_q;
                f_seq <= out_seq; out_seq <= out_seq + 32'd1; tx_len <= LEN_ORDER; cur_order_id <= c_id;
                f_csum <= (BUILD_MODE == 1) ? 16'h0000 : csum_next; ev_cancel_sent <= 1'b1;
                if (!(done_sent && need_cancel)) cancel_pend <= 1'b0;
            end else if (start_order) begin
                kind <= K_ORDER; f_cancel <= 1'b0; f_id <= o_id; f_s <= o_s; f_i <= o_i; f_p <= o_p; f_q <= o_q;
                f_seq <= out_seq; out_seq <= out_seq + 32'd1; tx_len <= LEN_ORDER; cur_order_id <= o_id;
                f_csum <= (BUILD_MODE == 1) ? 16'h0000 : csum_next; ev_order_sent <= 1'b1; s_start <= 1'b1;
            end else if (start_arp) begin
                kind <= K_ARP; arp_pend <= 1'b0; tx_len <= LEN_ARP; ev_arp_sent <= 1'b1;
            end
            if (start_cancel || start_order || start_arp) begin
                if (BUILD_MODE == 2) begin asm_busy <= 1'b1; asm_i <= '0; end
                else begin tx_start <= 1'b1; sending <= 1'b1; end
                cs_acc <= 32'h4500 + 32'd52 + 32'h4000 + 32'h4011 + {16'h0, out_seq[15:0]}; cs_i <= 4'd0;
            end
            // BUILD_MODE 1: the checksum after the start, one address word a clock (ready long before byte 24 is due)
            if (BUILD_MODE == 1 && cs_i != 4'd5 && sending) begin
                case (cs_i)
                    4'd0: cs_acc <= cs_acc + {16'h0, my_ip[31:16]};
                    4'd1: cs_acc <= cs_acc + {16'h0, my_ip[15:0]};
                    4'd2: cs_acc <= cs_acc + {16'h0, dst_ip[31:16]};
                    4'd3: cs_acc <= cs_acc + {16'h0, dst_ip[15:0]};
                    default: begin
                        logic [31:0] s;
                        s = {16'h0, cs_acc[15:0]} + {16'h0, cs_acc[31:16]};
                        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
                        f_csum <= ~s[15:0];
                    end
                endcase
                cs_i <= cs_i + 4'd1;
            end
            if (asm_busy) begin
                asm_i <= asm_i + 11'd1;
                if (asm_i + 11'd1 == tx_len) begin asm_busy <= 1'b0; asm_done <= 1'b1; end
            end
            if (asm_done) begin asm_done <= 1'b0; tx_start <= 1'b1; sending <= 1'b1; end
            if (tx_last && sending) sending <= 1'b0;
            // soft reset: drop what has not started, never an undo (no order or ARP reply starts in this clock)
            if (soft_rst) begin
                rq_valid <= 1'b0; arp_pend <= 1'b0;
                if (s_act && !s_start) begin
                    s_act <= 1'b0; s_wait <= 1'b0; s_gnt <= 1'b0; s_vk <= 1'b0; s_vg <= 1'b0; s_age <= '0;
                end
            end
        end
    end
    assign tx_kind   = sending ? kind : K_NONE;
    assign tx_poison = order_tx && s_act && s_start && bad_e;
endmodule
