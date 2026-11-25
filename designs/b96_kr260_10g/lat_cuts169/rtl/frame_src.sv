// frame_src.sv: builds one Ethernet/IPv4/UDP frame in Bench Feed v1 format (designs/b58a_trigger/docs/bench_feed_v1.md) word by word
// for mac64_tx (brief 96). One module serves the order frames of the trading path, the feed frames of the loop test, the probe frames of
// the echo measurement and the pseudo-random test frames of the self-test. Kinds: 0 order (NEW_ORDER 0x10, buy), 1 feed (ADD, ask),
// 2 probe (our own echo frame, UDP port probe), 3 test. Frames are LEN bytes (66 to 1514, without the FCS); the bytes after the
// 66-byte template are pseudo-random (xorshift, the same sequence every frame).
//
// The words that depend only on the configuration (0 to 4) are ready the clock after `start`; the live fields (instrument, price, quantity,
// sequence) are sampled each clock until word 4 is loaded, because they arrive from another clock domain a few clocks after `start`
// (the order path); `stale` counts frames whose sampled sequence did not equal `want_seq` (the data bus was not yet settled).
// Brief 169 (FAST = 1): `fast` (combinational, with `start`) says the MAC took word 0 in this very clock (mac64_tx FAST_PRE): the source starts at word 1, and
// the check of the sampled sequence moves one word later (the live fields are still sampled until word 3 is loaded, so the frame carries the same samples as the base).
// FAST = 0 (the default): the base file.
module frame_src #(
    parameter bit FAST = 1'b0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        fast,           // brief 169: the MAC took word 0 in this clock (FAST = 1 only)
    input  logic        clr,            // clear `stale` (the counter clear)
    input  logic [1:0]  kind,
    input  logic [15:0] len,
    input  logic [47:0] dst_mac,        // byte 0 (first on the wire) in bits 7:0
    input  logic [47:0] src_mac,
    input  logic [31:0] src_ip,         // first octet in bits 31:24
    input  logic [31:0] dst_ip,
    input  logic [15:0] sport,
    input  logic [15:0] dport_order, dport_feed, dport_probe,
    input  logic [15:0] b_inst,         // live fields (sampled until word 4 is loaded)
    input  logic [31:0] b_price,
    input  logic [31:0] b_qty,
    input  logic [31:0] b_seq,
    input  logic [31:0] want_seq,
    output logic        busy,
    output logic [31:0] stale,
    output logic        stale_p,        // one clock: this frame's sampled sequence did not equal `want_seq` (the clock `stale` counts it)
    output logic [31:0] seq_seen,       // the sequence the frame carries (valid with stale_p)
    output logic        s_valid,
    output logic [63:0] s_data,
    output logic        s_last,
    output logic [2:0]  s_nb1,
    input  logic        s_ready
);
    logic [15:0]  len_c;      // the length asked for, clamped to 66 to 1514 bytes (a shorter frame would be a runt or underflow the IP length)
    assign len_c = (len < 16'd66) ? 16'd66 : (len > 16'd1514) ? 16'd1514 : len;
    logic [1:0]   k_r;
    logic [15:0]  len_r;
    logic [15:0]  idx, last_idx;
    logic [15:0]  f_inst;
    logic [31:0]  f_price, f_qty, f_seq;
    logic [63:0]  xr;
    logic [15:0]  ip_csum;
    // fields of the template
    logic [15:0]  totlen, udplen, dport;
    logic [7:0]   mtype, mside;
    logic [527:0] V;
    assign totlen = len_r - 16'd14;
    assign udplen = len_r - 16'd34;
    assign dport  = (k_r == 2'd0) ? dport_order : (k_r == 2'd1) ? dport_feed : dport_probe;
    assign mtype  = (k_r == 2'd1 || k_r == 2'd3) ? 8'h01 : 8'h10;
    assign mside  = (k_r == 2'd1 || k_r == 2'd3) ? 8'h01 : 8'h00;
    // IPv4 header checksum: kept up to date every clock (the inputs are static while a frame is built)
    logic [31:0] sum;
    always_comb begin
        sum = 32'h4500 + {16'd0, totlen} + 32'h4000 + 32'h4011 + {16'd0, src_ip[31:16]} + {16'd0, src_ip[15:0]}
            + {16'd0, dst_ip[31:16]} + {16'd0, dst_ip[15:0]};
    end
    logic [31:0] sum1;
    assign sum1 = {16'd0, sum[15:0]} + {16'd0, sum[31:16]};
    always_ff @(posedge clk) ip_csum <= ~(sum1[15:0] + {15'd0, sum1[16]});
    function automatic logic [527:0] build(input logic [47:0] dm, sm, input logic [15:0] tl, ul, dp, csum, spt, inst,
                                           input logic [31:0] sip, dip, seq, price, qty, ref_, input logic [7:0] ty, sd);
        logic [527:0] v;
        v = '0;
        for (int i = 0; i < 6; i++) begin v[8 * i +: 8] = dm[8 * i +: 8]; v[8 * (6 + i) +: 8] = sm[8 * i +: 8]; end
        v[8 * 12 +: 8] = 8'h08; v[8 * 13 +: 8] = 8'h00; v[8 * 14 +: 8] = 8'h45; v[8 * 15 +: 8] = 8'h00;
        v[8 * 16 +: 8] = tl[15:8]; v[8 * 17 +: 8] = tl[7:0];
        v[8 * 20 +: 8] = 8'h40; v[8 * 22 +: 8] = 8'h40; v[8 * 23 +: 8] = 8'h11;
        v[8 * 24 +: 8] = csum[15:8]; v[8 * 25 +: 8] = csum[7:0];
        for (int i = 0; i < 4; i++) begin v[8 * (26 + i) +: 8] = sip[8 * (3 - i) +: 8]; v[8 * (30 + i) +: 8] = dip[8 * (3 - i) +: 8]; end
        v[8 * 34 +: 8] = spt[15:8]; v[8 * 35 +: 8] = spt[7:0];
        v[8 * 36 +: 8] = dp[15:8];  v[8 * 37 +: 8] = dp[7:0];
        v[8 * 38 +: 8] = ul[15:8];  v[8 * 39 +: 8] = ul[7:0];
        v[8 * 42 +: 8] = 8'h42; v[8 * 43 +: 8] = 8'h46; v[8 * 44 +: 8] = 8'h01; v[8 * 45 +: 8] = 8'h01;
        for (int i = 0; i < 4; i++) begin
            v[8 * (46 + i) +: 8] = seq[8 * (3 - i) +: 8];
            v[8 * (54 + i) +: 8] = price[8 * (3 - i) +: 8];
            v[8 * (58 + i) +: 8] = qty[8 * (3 - i) +: 8];
            v[8 * (62 + i) +: 8] = ref_[8 * (3 - i) +: 8];
        end
        v[8 * 50 +: 8] = ty; v[8 * 51 +: 8] = sd; v[8 * 52 +: 8] = inst[15:8]; v[8 * 53 +: 8] = inst[7:0];
        return v;
    endfunction
    assign V = build(dst_mac, src_mac, totlen, udplen, dport, ip_csum, sport, f_inst, src_ip, dst_ip, f_seq, f_price, f_qty, f_seq, mtype, mside);
    function automatic logic [63:0] xs(input logic [63:0] x);
        logic [63:0] y; y = x ^ (x << 13); y = y ^ (y >> 7); return y ^ (y << 17);
    endfunction
    logic [15:0] nidx;
    logic [63:0] nword;
    assign nidx  = s_ready ? idx + 16'd1 : idx;
    assign nword = (nidx >= 16'd9) ? ((s_ready && idx >= 16'd8) ? xs(xr) : xr) : V[64 * nidx[3:0] +: 64];
    assign s_last = (idx == last_idx);
    assign s_nb1  = s_last ? 3'(len_r - 16'd8 * last_idx - 16'd1) : 3'd7;
    logic [15:0] ck_idx;     // the word at which the sampled sequence is checked: 3, or 4 for a frame started at word 1
    assign stale_p = busy && idx == ck_idx && s_ready && (f_seq != want_seq);
    assign seq_seen = f_seq;
    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; s_valid <= 1'b0; idx <= '0; stale <= '0; s_data <= '0; xr <= 64'h9E3779B97F4A7C15; k_r <= '0; len_r <= 16'd66;
            f_inst <= '0; f_price <= '0; f_qty <= '0; f_seq <= '0; last_idx <= '0; ck_idx <= 16'd3;
        end else begin
            if (!busy || idx < 16'd4) begin
                f_inst <= b_inst; f_price <= b_price; f_qty <= b_qty; f_seq <= b_seq;
            end
            if (start && !busy) begin
                busy <= 1'b1; k_r <= kind; len_r <= len_c; idx <= '0; s_valid <= 1'b1;
                last_idx <= (len_c - 16'd1) >> 3;
                xr <= 64'h9E3779B97F4A7C15;
                ck_idx <= 16'd3;
                // word 0 holds only configuration fields: build it from the inputs the template uses
                s_data <= {src_mac[15:0], dst_mac};
                if (FAST && fast) begin idx <= 16'd1; ck_idx <= 16'd4; s_data <= V[127:64]; end     // word 1 holds only the two MAC addresses, the EtherType and the IPv4 version
            end else if (busy) begin
                if (idx == ck_idx && s_ready) stale <= stale + ((f_seq != want_seq) ? 32'd1 : 32'd0);
                if (s_ready) begin
                    if (s_last) begin busy <= 1'b0; s_valid <= 1'b0; end
                    idx <= idx + 16'd1;
                    s_data <= nword;
                    if (idx >= 16'd8) xr <= xs(xr);
                end
            end
            if (clr) stale <= '0;
        end
    end
endmodule
