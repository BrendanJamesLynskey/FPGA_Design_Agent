// order_seg.sv: the order frame of brief 110 (ouch_enter's 59-byte SoupBinTCP packet) inside a 113-byte Ethernet/IPv4/TCP frame, as a stream of fifteen 64-bit words (brief 127).
//
// THIS IS THE STAND-IN for brief 119's tcp_fast (PR #245): it has the same order-side ports and the same segment output (o_v, o_d, o_sof, o_eof, o_keep, o_poison), so
// that file replaces this one when #245 is merged (order_seg_tcpfast.sv, same module name; docs/itch_integration.md section 8). What the stand-in does and does not do:
//   * 14 byte Ethernet header (destination = the venue MAC, source = our MAC), 20 byte IPv4 header (ID 0, DF, TTL 64, protocol 6, total length 99, header checksum computed
//     from the addresses), 20 byte TCP header (ports from the configuration, sequence number = tpl_seq0 plus 59 for every segment that left unpoisoned, acknowledgement number
//     tpl_ack, PSH+ACK, window 0xFFFF), then the 59 bytes of ouch_enter. The frame check sequence is the MAC's.
//   * The TCP CHECKSUM FIELD IS 0: this is NOT a valid TCP segment, the receiving TCP stack would drop it. The loopback and our own receiver do not look at it; a real
//     exchange or a Linux host needs tcp_fast. The sequence number is not tracked against anything (no acknowledgements are read).
//   * It is not an arbiter: the transmit multiplexer (tx_mux) decides whether the frame gets the MAC; a frame that finds the MAC busy is dropped there and counted.
// Timing (clock G = the clock `go` is high): word 0 is in o_d in G+1 (o_sof), word i in G+1+i, word 14 (one byte, o_keep 0x01, o_eof) in G+15. The payload bytes come from
// ouch_enter, which starts its own eight words in G+1; word 6+j needs ouch word j, which is stored long before it is used (ouch word j is out in G+1+j). The segment is
// 15 clocks long; `busy` (to risk_glue) is high from G+1 to the clock after the last word.
// Abort: an abort (risk reject, or a speculative candidate with no book update) while the frame is in flight does not stop the stream (the MAC needs every word); the
// frame is finished and o_poison is set with its last word, and the MAC makes the frame check sequence wrong. A speculative frame still without a verdict at its last word
// is poisoned too (fail closed). An abort after the last word (`late`) is counted by ouch_enter and cannot be undone.
module order_seg (
    input  logic        clk,
    input  logic        rst,
    // order side: the ports of ouch_enter
    input  logic        go,
    input  logic        go_spec,
    input  logic [63:0] f_sym,
    input  logic [31:0] f_px,
    input  logic [31:0] f_qty,
    input  logic [31:0] f_ref,
    input  logic        commit,
    input  logic        abort,
    input  logic [7:0]  cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic [31:0] cfg_minqty,
    // segment template (this stand-in) and software bus (tcp_fast only; read as 0 here)
    input  logic [47:0] tpl_my_mac, tpl_venue_mac,
    input  logic [31:0] tpl_my_ip, tpl_venue_ip,
    input  logic [15:0] tpl_sport, tpl_dport,
    input  logic [31:0] tpl_seq0, tpl_ack,
    input  logic        tpl_load,        // pulse: tpl_seq0 becomes the next sequence number
    input  logic        sw_we,
    input  logic [4:0]  sw_waddr,
    input  logic [31:0] sw_wdata,
    input  logic [4:0]  sw_raddr,
    output logic [31:0] sw_rdata,
    output logic        busy,
    output logic        late,
    output logic        spec_pend,
    // segment out
    output logic        o_v,
    output logic [63:0] o_d,
    output logic        o_sof,
    output logic        o_eof,
    output logic [7:0]  o_keep,
    output logic        o_poison,        // with the last word: the frame check sequence must be made wrong
    output logic        o_unres          // one clock, with the last word: poisoned because the verdict was still missing
);
    // ---- ouch_enter, unchanged
    logic        ou_busy, ou_v, ou_sof, ou_eof, ou_abort;
    logic [63:0] ou_d;
    logic [7:0]  ou_keep;
    logic        act;
    logic        start;
    logic        ou_late;
    assign late  = abort && !act && !ou_busy;
    assign busy  = ou_busy || act;
    assign start = go && !ou_busy && !act && !abort;
    ouch_enter u_o (.clk, .rst, .go(go && !act), .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
                    .cfg_custtype, .cfg_minqty, .busy(ou_busy), .late(ou_late), .spec_pend, .o_v(ou_v), .o_d(ou_d), .o_sof(ou_sof), .o_eof(ou_eof), .o_keep(ou_keep), .o_abort(ou_abort));
    assign sw_rdata = 32'd0;

    // ---- the payload, stored as it comes
    logic [63:0] pw [0:7];
    logic [2:0]  pi;
    always_ff @(posedge clk) begin
        if (ou_v) begin
            pw[ou_sof ? 3'd0 : pi] <= ou_d;
            pi <= (ou_sof ? 3'd0 : pi) + 3'd1;
        end
    end

    // ---- IPv4 header checksum of the static fields (a pipeline: the inputs do not change while orders go out)
    logic [16:0] ck_a, ck_b;
    logic [19:0] ck_s;
    logic [16:0] ck_f;
    logic [15:0] ck;
    always_ff @(posedge clk) begin
        ck_a <= {1'b0, tpl_my_ip[31:16]} + {1'b0, tpl_my_ip[15:0]};
        ck_b <= {1'b0, tpl_venue_ip[31:16]} + {1'b0, tpl_venue_ip[15:0]} + 17'hC569;       // 0x4500 + 0x0063 + 0x0000 + 0x4000 + 0x4006
        ck_s <= {3'd0, ck_a} + {3'd0, ck_b};
        ck_f <= {1'b0, ck_s[15:0]} + {13'd0, ck_s[19:16]};
        ck   <= ~(ck_f[15:0] + {15'd0, ck_f[16]});
    end

    // ---- the segment
    logic [3:0]  si;
    logic [31:0] snd_nxt;
    logic        ab_l;
    logic [63:0] w;
    always_comb begin
        w = '0;
        case (si)
            4'd0: w = {tpl_my_mac[15:0], tpl_venue_mac};
            4'd1: w = {16'h0045, 16'h0008, tpl_my_mac[47:16]};
            4'd2: w = 64'h0640_0040_0000_6300;
            4'd3: w = {tpl_venue_ip[23:16], tpl_venue_ip[31:24], tpl_my_ip[7:0], tpl_my_ip[15:8], tpl_my_ip[23:16], tpl_my_ip[31:24], ck[7:0], ck[15:8]};
            4'd4: w = {snd_nxt[23:16], snd_nxt[31:24], tpl_dport[7:0], tpl_dport[15:8], tpl_sport[7:0], tpl_sport[15:8], tpl_venue_ip[7:0], tpl_venue_ip[15:8]};
            4'd5: w = {8'h18, 8'h50, tpl_ack[7:0], tpl_ack[15:8], tpl_ack[23:16], tpl_ack[31:24], snd_nxt[7:0], snd_nxt[15:8]};
            4'd6: w = {pw[0][15:0], 48'h0000_0000_FFFF};
            4'd7: w = {pw[1][15:0], pw[0][63:16]};
            4'd8: w = {pw[2][15:0], pw[1][63:16]};
            4'd9: w = {pw[3][15:0], pw[2][63:16]};
            4'd10: w = {pw[4][15:0], pw[3][63:16]};
            4'd11: w = {pw[5][15:0], pw[4][63:16]};
            4'd12: w = {pw[6][15:0], pw[5][63:16]};
            4'd13: w = {pw[7][15:0], pw[6][63:16]};
            4'd14: w = {40'd0, pw[7][23:16]};
            default: w = '0;
        endcase
    end
    logic unres;
    assign unres = spec_pend && !commit && !abort;
    always_ff @(posedge clk) begin
        o_v <= 1'b0; o_sof <= 1'b0; o_eof <= 1'b0; o_poison <= 1'b0; o_unres <= 1'b0;
        if (rst) begin
            act <= 1'b0; si <= '0; snd_nxt <= '0; ab_l <= 1'b0; o_d <= '0; o_keep <= '0; pi <= '0;
        end else begin
            if (tpl_load) snd_nxt <= tpl_seq0;
            if (abort && act) ab_l <= 1'b1;
            if (start) begin
                act <= 1'b1; si <= 4'd1; ab_l <= 1'b0;
                o_v <= 1'b1; o_sof <= 1'b1; o_d <= {tpl_my_mac[15:0], tpl_venue_mac}; o_keep <= 8'hFF;
            end else if (act) begin
                o_v <= 1'b1; o_d <= w; o_keep <= 8'hFF;
                si <= si + 4'd1;
                if (si == 4'd14) begin
                    act <= 1'b0; o_eof <= 1'b1; o_keep <= 8'h01;
                    o_poison <= ab_l || abort || unres; o_unres <= !(ab_l || abort) && unres;
                    if (!(ab_l || abort || unres)) snd_nxt <= snd_nxt + 32'd59;
                end
            end
        end
    end
    logic _unused;
    assign _unused = &{1'b0, ou_late, ou_eof, ou_abort, ou_keep, sw_we, sw_waddr, sw_wdata, sw_raddr, go_spec};
endmodule
