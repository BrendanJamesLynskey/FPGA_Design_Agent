// feed_rx.sv: cut-through receive parser for the bench loop: Ethernet II, IPv4 (no options, no fragments, header
// checksum checked), UDP to our port, then the Bench Feed v1 payload (docs/bench_feed_v1.md), plus ARP requests for
// our address.
//
// Every check is made on the byte that completes its field, while the frame is still arriving. Feed messages are
// reported field by field:
//   msg_inst_v  the instrument field is complete (book read can start)
//   msg_px_v    the price field is complete: type, side, instrument and price are valid (the decision point)
//   msg_end_v   the whole 16-byte message is in: size and reference also valid (the book update point)
// The frame's verdict (FCS, length, RX_ER) comes later from mac_rx; frame_end_v passes it on with what was parsed.
// Header layout (byte index from the destination address):
//   0-5 dst MAC (ours, or broadcast for ARP)  6-11 src MAC  12-13 EtherType 0x0800 or 0x0806
//   IPv4 14: 0x45, 16-17 total length, 20-21 flags/fragment (MF and offset must be 0), 23 protocol 17,
//   24-25 header checksum, 26-29 source, 30-33 destination (ours)
//   UDP 34-35 source port, 36-37 destination port (ours), 38-39 length, 40-41 checksum (not checked), payload from 42
//   ARP 14: htype 1, ptype 0x0800, 6, 4, oper 1; sender MAC 22-27, sender IP 28-31, target IP 38-41 (ours)
// Not handled (dropped and counted): VLAN tags, IPv4 options, fragments, protocols other than UDP.

module feed_rx #(
    parameter int MAX_MSGS = 91         // messages per packet (a 1500-byte IP datagram holds 91)
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [47:0] my_mac,
    input  logic [31:0] my_ip,
    input  logic [15:0] my_port,
    // from mac_rx
    input  logic        in_valid,
    input  logic        in_sof,
    input  logic [7:0]  in_data,
    input  logic [10:0] in_idx,
    input  logic        in_end_v,
    input  logic        in_end_good,
    // feed events
    output logic        pkt_hdr_v,      // a packet header with the right magic, version and length
    output logic [31:0] pkt_seq,
    output logic [7:0]  pkt_cnt,
    output logic        msg_inst_v,
    output logic        msg_px_v,
    output logic        msg_end_v,
    output logic [7:0]  msg_type,
    output logic        msg_side,
    output logic [15:0] msg_inst,
    output logic [31:0] msg_px,
    output logic [31:0] msg_size,
    output logic [31:0] msg_ref,
    output logic [31:0] msg_seq,
    output logic        msg_first,      // the message is the first of its frame
    // end of frame
    output logic        frame_end_v,
    output logic        frame_good,     // mac_rx verdict
    output logic        frame_feed,     // a feed packet for us (header passed)
    output logic        frame_arp_req,  // an ARP request for our address
    output logic [47:0] arp_sha,
    output logic [31:0] arp_spa,
    // drops (one clock each; at most one per frame, the first reason)
    output logic        ev_drop_l2,     // destination MAC not ours (or broadcast that is not ARP)
    output logic        ev_drop_type,   // EtherType not IPv4/ARP (VLAN tags included)
    output logic        ev_drop_ip,     // IPv4 not for us: version/IHL, fragment, protocol, destination
    output logic        ev_drop_csum,   // IPv4 header checksum wrong
    output logic        ev_drop_port,   // UDP destination port not ours
    output logic        ev_drop_feed,   // payload: magic, version, count or length wrong
    output logic        ev_drop_arp     // ARP that is not a request for our address
);
    localparam logic [15:0] MAGIC = 16'h4246;     // "BF"

    // per-frame state
    logic        alive;                 // no check has failed yet
    logic        is_arp, bcast, mac_us, mac_bc;
    logic [31:0] csum;
    logic [15:0] udp_len;
    logic [15:0] w16;                   // previous byte in [15:8]
    logic [47:0] sha_sh;
    logic [31:0] spa_sh, tpa_sh;
    logic [7:0]  cnt_r;
    logic [7:0]  k;                     // message number
    logic [3:0]  off;                   // byte within the message
    logic        in_msgs;
    logic [7:0]  ty;
    logic        sd;
    logic [15:0] inst;
    logic [31:0] px, sz, rf;
    logic [31:0] seq_r;
    logic        hdr_ok;

    logic [10:0] b;
    logic [7:0]  d;
    assign b = in_idx;
    assign d = in_data;

    // the payload offset and the bytes of the field being completed
    logic [10:0] p;
    assign p = b - 11'd42;
    logic [15:0] word;                  // this byte with the previous one
    assign word = {w16[15:8], d};
    logic [31:0] csum_next, csum_fold;
    always_comb begin
        csum_next = csum + {16'h0, word};
        csum_fold = {16'h0, csum_next[15:0]} + {16'h0, csum_next[31:16]};
        csum_fold = {16'h0, csum_fold[15:0]} + {16'h0, csum_fold[31:16]};
    end
    logic [7:0] my_mac_b, my_ip_b;
    always_comb begin
        case (b[2:0])                    // b in 0..5
            3'd0: my_mac_b = my_mac[47:40];
            3'd1: my_mac_b = my_mac[39:32];
            3'd2: my_mac_b = my_mac[31:24];
            3'd3: my_mac_b = my_mac[23:16];
            3'd4: my_mac_b = my_mac[15:8];
            default: my_mac_b = my_mac[7:0];
        endcase
        case (b)                         // IPv4 destination 30..33, ARP target 38..41
            11'd30, 11'd38: my_ip_b = my_ip[31:24];
            11'd31, 11'd39: my_ip_b = my_ip[23:16];
            11'd32, 11'd40: my_ip_b = my_ip[15:8];
            default:        my_ip_b = my_ip[7:0];
        endcase
    end

    // drop helper: the first failing check of a frame raises one event
    logic        fail;
    logic [2:0]  why;
    localparam logic [2:0] W_L2 = 3'd0, W_TYPE = 3'd1, W_IP = 3'd2, W_CSUM = 3'd3, W_PORT = 3'd4, W_FEED = 3'd5,
                           W_ARP = 3'd6;
    always_comb begin
        fail = 1'b0; why = W_L2;
        if (in_valid && alive) begin
            if (b == 11'd5 && !((mac_us && d == my_mac_b) || (mac_bc && d == 8'hFF))) begin fail = 1'b1; why = W_L2; end
            else if (b == 11'd13) begin
                if (word == 16'h0806) begin end
                else if (word != 16'h0800)   begin fail = 1'b1; why = W_TYPE; end
                else if (bcast)              begin fail = 1'b1; why = W_L2; end
            end else if (is_arp) begin
                if ((b == 11'd15 && word != 16'h0001) || (b == 11'd17 && word != 16'h0800) ||
                    (b == 11'd19 && word != 16'h0604) || (b == 11'd21 && word != 16'h0001) ||
                    (b >= 11'd38 && b <= 11'd41 && d != my_ip_b)) begin fail = 1'b1; why = W_ARP; end
            end else begin
                if ((b == 11'd14 && d != 8'h45) || (b == 11'd21 && (word & 16'h3FFF) != 16'h0) ||
                    (b == 11'd23 && d != 8'd17) || (b >= 11'd30 && b <= 11'd33 && d != my_ip_b))
                    begin fail = 1'b1; why = W_IP; end
                else if (b == 11'd33 && csum_fold[15:0] != 16'hFFFF) begin fail = 1'b1; why = W_CSUM; end
                else if (b == 11'd37 && word != my_port) begin fail = 1'b1; why = W_PORT; end
                else if (b == 11'd39 && word < 16'd16) begin fail = 1'b1; why = W_FEED; end
                else if ((b == 11'd43 && word != MAGIC) || (b == 11'd44 && d != 8'h01) ||
                         (b == 11'd45 && (d == 8'h00 || d > 8'(MAX_MSGS) ||
                                          {5'd0, d, 4'd0} + 17'd16 > {1'b0, udp_len})))
                    begin fail = 1'b1; why = W_FEED; end
            end
        end
    end

    always_ff @(posedge clk) begin
        {ev_drop_l2, ev_drop_type, ev_drop_ip, ev_drop_csum, ev_drop_port, ev_drop_feed, ev_drop_arp} <= '0;
        pkt_hdr_v <= 1'b0; msg_inst_v <= 1'b0; msg_px_v <= 1'b0; msg_end_v <= 1'b0; frame_end_v <= 1'b0;
        if (rst) begin
            alive <= 1'b0; is_arp <= 1'b0; bcast <= 1'b0; mac_us <= 1'b0; mac_bc <= 1'b0; csum <= '0; udp_len <= '0; w16 <= '0; cnt_r <= '0; k <= '0;
            off <= '0; in_msgs <= 1'b0; hdr_ok <= 1'b0; seq_r <= '0; ty <= '0; sd <= 1'b0; inst <= '0; px <= '0;
            sz <= '0; rf <= '0; sha_sh <= '0; spa_sh <= '0; tpa_sh <= '0;
            frame_good <= 1'b0; frame_feed <= 1'b0; frame_arp_req <= 1'b0; arp_sha <= '0; arp_spa <= '0;
            pkt_seq <= '0; pkt_cnt <= '0; msg_type <= '0; msg_side <= 1'b0; msg_inst <= '0; msg_px <= '0;
            msg_size <= '0; msg_ref <= '0; msg_seq <= '0; msg_first <= 1'b0;
        end else begin
            if (in_valid) begin
                w16 <= {d, 8'h00};
                if (in_sof) begin
                    alive  <= 1'b1;
                    mac_us <= (d == my_mac[47:40]);
                    mac_bc <= (d == 8'hFF);
                    is_arp <= 1'b0; csum <= '0; hdr_ok <= 1'b0; in_msgs <= 1'b0; k <= '0; off <= '0;
                end else begin
                    if (fail) begin
                        alive <= 1'b0;
                        case (why)
                            W_L2:    ev_drop_l2   <= 1'b1;
                            W_TYPE:  ev_drop_type <= 1'b1;
                            W_IP:    ev_drop_ip   <= 1'b1;
                            W_CSUM:  ev_drop_csum <= 1'b1;
                            W_PORT:  ev_drop_port <= 1'b1;
                            W_FEED:  ev_drop_feed <= 1'b1;
                            default: ev_drop_arp  <= 1'b1;
                        endcase
                    end
                    if (b <= 11'd5) begin
                        mac_us <= mac_us && d == my_mac_b;
                        mac_bc <= mac_bc && d == 8'hFF;
                    end
                    if (b == 11'd5) bcast <= !(mac_us && d == my_mac_b);
                    if (b == 11'd13) is_arp <= (word == 16'h0806);
                end
                // IPv4 header checksum over bytes 14..33 (word ends on odd b)
                if (b >= 11'd15 && b <= 11'd33 && b[0]) csum <= csum_fold;
                if (b == 11'd39) udp_len <= word;
                if (b >= 11'd22 && b <= 11'd27) sha_sh <= {sha_sh[39:0], d};
                if (b >= 11'd28 && b <= 11'd31) spa_sh <= {spa_sh[23:0], d};
                // feed header: 42-43 magic, 44 version, 45 count, 46-49 sequence
                if (b == 11'd45) cnt_r <= d;
                if (b >= 11'd46 && b <= 11'd49) seq_r <= {seq_r[23:0], d};
                if (b == 11'd49 && alive && !fail && !is_arp) begin
                    hdr_ok <= 1'b1; in_msgs <= 1'b1; k <= '0; off <= '0;
                    pkt_hdr_v <= 1'b1; pkt_seq <= {seq_r[23:0], d}; pkt_cnt <= cnt_r;
                end
                // messages from byte 50, 16 bytes each
                if (in_msgs && alive && b >= 11'd50) begin
                    off <= off + 4'd1;
                    case (off)
                        4'd0: ty <= d;
                        4'd1: sd <= d[0];
                        4'd2: inst[15:8] <= d;
                        4'd3: begin
                            inst[7:0] <= d;
                            msg_inst_v <= 1'b1; msg_inst <= {inst[15:8], d};
                        end
                        4'd4, 4'd5, 4'd6: px <= {px[23:0], d};
                        4'd7: begin
                            px <= {px[23:0], d};
                            msg_px_v <= 1'b1; msg_type <= ty; msg_side <= sd; msg_inst <= inst;
                            msg_px <= {px[23:0], d}; msg_seq <= pkt_seq + {24'd0, k}; msg_first <= (k == 8'd0);
                        end
                        4'd8, 4'd9, 4'd10, 4'd11: sz <= {sz[23:0], d};
                        4'd12, 4'd13, 4'd14: rf <= {rf[23:0], d};
                        default: begin
                            msg_end_v <= 1'b1; msg_size <= sz; msg_ref <= {rf[23:0], d};
                            k <= k + 8'd1;
                            if (k + 8'd1 == cnt_r) in_msgs <= 1'b0;
                        end
                    endcase
                end
            end
            if (in_end_v) begin
                frame_end_v   <= 1'b1;
                frame_good    <= in_end_good;
                frame_feed    <= hdr_ok && alive;
                frame_arp_req <= is_arp && alive && b >= 11'd41;
                arp_sha       <= sha_sh;
                arp_spa       <= spa_sh;
                alive <= 1'b0; in_msgs <= 1'b0;
            end
        end
    end
endmodule
