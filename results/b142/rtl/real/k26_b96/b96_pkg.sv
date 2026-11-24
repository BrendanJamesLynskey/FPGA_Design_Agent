// b96_pkg.sv: the 10GBASE-R block codes, scrambler and CRC-32 of brief 96, as functions on packed vectors.
//
// XGMII convention: lane i is bits 8i+7:8i of a 64-bit word and bit i of the 8-bit control vector (1 = control character).
// Control characters: idle 07, start FB, terminate FD, error FE. A 66-bit block is {payload[63:0], sync header[1:0]}: the
// header is sent first, then the payload least significant bit first (IEEE 802.3 clause 49 block formats, Figure 49-7).
// Written with variable indexes inside loops (no constant part selects of function arguments), which Icarus, Verilator
// and xsim all accept (the lesson of brief 56A's prbs64.sv).
package b96_pkg;
    localparam logic [7:0] X_IDLE = 8'h07, X_START = 8'hFB, X_TERM = 8'hFD, X_ERR = 8'hFE;
    localparam logic [7:0] T_CTRL = 8'h1E, T_S0 = 8'h78, T_S4 = 8'h33;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam int CFGW = 421;     // width of the configuration vector (b96_core)
    // Brief 96C: the receive-domain status words (RXV, docs/register_map.md) are produced in two clock domains: the PCS counters in the receive
    // user clock (the write side of rate_match) and the MAC, trade and rate-match read-side counters in the core clock. Bit i of RXV_OWN_W is 1 when
    // word i belongs to the receive clock; the two vectors carry their own words packed in order of index.
    localparam int          NRXW      = 29;
    localparam logic [31:0] RXV_OWN_W = 32'h000C_807F;   // words 0-6, 15, 18, 19
    function automatic int rxv_pos(input logic own, input int i);     // position of word i among the words of its own domain
        int n; n = 0;
        for (int k = 0; k < i; k++) if (RXV_OWN_W[k] == own) n++;
        return n;
    endfunction
    function automatic int rxv_count(input logic own);
        int n; n = 0;
        for (int k = 0; k < NRXW; k++) if (RXV_OWN_W[k] == own) n++;
        return n;
    endfunction
    localparam int NRXV_W = rxv_count(1'b1);     // words in the receive-clock vector
    localparam int NRXV_C = rxv_count(1'b0);     // words in the core-clock vector

    // terminate block type of lane k
    function automatic logic [7:0] t_term(input int k);
        case (k)
            0: return 8'h87; 1: return 8'h99; 2: return 8'hAA; 3: return 8'hB4;
            4: return 8'hCC; 5: return 8'hD2; 6: return 8'hE1; default: return 8'hFF;
        endcase
    endfunction

    // ------------------------------------------------------------------------------------------------------ scrambler
    // x^58 + x^39 + 1, self-synchronising. hist[0] is the newest scrambled bit (after a word: hist[j] = out[63-j]).
    function automatic logic [63:0] scr_out(input logic [57:0] hist, input logic [63:0] d);
        logic [63:0] o; logic a, b;
        for (int i = 0; i < 64; i++) begin
            if (i < 39) a = hist[38 - i]; else a = o[i - 39];
            if (i < 58) b = hist[57 - i]; else b = o[i - 58];
            o[i] = d[i] ^ a ^ b;
        end
        return o;
    endfunction
    function automatic logic [57:0] hist_next(input logic [63:0] scrambled);
        logic [57:0] h;
        for (int j = 0; j < 58; j++) h[j] = scrambled[63 - j];
        return h;
    endfunction
    function automatic logic [63:0] desc_out(input logic [57:0] hist, input logic [63:0] s);
        logic [63:0] o; logic a, b;
        for (int i = 0; i < 64; i++) begin
            if (i < 39) a = hist[38 - i]; else a = s[i - 39];
            if (i < 58) b = hist[57 - i]; else b = s[i - 58];
            o[i] = s[i] ^ a ^ b;
        end
        return o;
    endfunction

    // ------------------------------------------------------------------------------------------------------ encoder
    function automatic logic [6:0] ctl7(input logic [7:0] ch);
        return (ch == X_IDLE) ? 7'h00 : 7'h1E;
    endfunction
    function automatic logic [65:0] enc_err();
        logic [63:0] p; p = {8'h00, 56'h0};
        p[7:0] = T_CTRL;
        for (int i = 0; i < 8; i++) p[8 + 7 * i +: 7] = 7'h1E;
        return {p, 2'b10};
    endfunction
    // XGMII word -> 66-bit block. Words the MAC never produces (start in lane 4, ordered sets, malformed) become an error block.
    function automatic logic [65:0] enc66(input logic [63:0] d, input logic [7:0] c);
        logic [63:0] p; logic ok; logic [7:0] ch; logic [7:0] want;
        p = '0; ok = 1'b0;
        if (c == 8'h00) return {d, 2'b01};
        if (c == 8'hFF) begin
            ok = 1'b1;
            for (int i = 0; i < 8; i++) begin ch = d[8 * i +: 8]; if (ch != X_IDLE && ch != X_ERR) ok = 1'b0; end
            if (ok) begin
                p[7:0] = T_CTRL;
                for (int i = 0; i < 8; i++) p[8 + 7 * i +: 7] = ctl7(d[8 * i +: 8]);
                return {p, 2'b10};
            end
        end
        if (c == 8'h01 && d[7:0] == X_START) return {d[63:8], T_S0, 2'b10};
        for (int k = 0; k < 8; k++) begin
            want = 8'hFF << k;
            if (c == want && d[8 * k +: 8] == X_TERM) begin
                ok = 1'b1;
                for (int i = 0; i < 8; i++) if (i > k) begin ch = d[8 * i +: 8]; if (ch != X_IDLE && ch != X_ERR) ok = 1'b0; end
                if (ok) begin
                    p[7:0] = t_term(k);
                    for (int i = 0; i < 8; i++) begin
                        if (i < k) p[8 + 8 * i +: 8] = d[8 * i +: 8];
                        else if (i > k) p[8 + 8 * k + (7 - k) + 7 * (i - k - 1) +: 7] = ctl7(d[8 * i +: 8]);
                    end
                    return {p, 2'b10};
                end
            end
        end
        return enc_err();
    endfunction

    // ------------------------------------------------------------------------------------------------------ decoder
    // {note[1:0], c[7:0], d[63:0]}; note 0 normal, 1 invalid sync header, 2 unknown block type, 3 ordered set (shown as idles)
    function automatic logic [73:0] dec66(input logic [1:0] sh, input logic [63:0] p);
        logic [63:0] d; logic [7:0] c; logic [1:0] note; logic [7:0] t; int k; logic [6:0] code; logic found;
        d = '0; c = '0; note = 2'd0; t = p[7:0]; found = 1'b0;
        if (sh == 2'b01) return {2'd0, 8'h00, p};
        if (sh != 2'b10) begin
            for (int i = 0; i < 8; i++) d[8 * i +: 8] = X_ERR;
            return {2'd1, 8'hFF, d};
        end
        if (t == T_CTRL) begin
            for (int i = 0; i < 8; i++) begin code = p[8 + 7 * i +: 7]; d[8 * i +: 8] = (code == 7'h00) ? X_IDLE : X_ERR; end
            return {2'd0, 8'hFF, d};
        end
        if (t == T_S0) return {2'd0, 8'h01, p[63:8], X_START};
        if (t == T_S4) begin
            for (int i = 0; i < 4; i++) begin code = p[8 + 7 * i +: 7]; d[8 * i +: 8] = (code == 7'h00) ? X_IDLE : X_ERR; end
            d[39:32] = X_START; d[63:40] = p[63:40];
            return {2'd0, 8'h1F, d};
        end
        for (int kk = 0; kk < 8; kk++) begin
            if (t == t_term(kk)) begin
                found = 1'b1; k = kk;
                for (int i = 0; i < 8; i++) begin
                    if (i < k) d[8 * i +: 8] = p[8 + 8 * i +: 8];
                    else if (i == k) d[8 * i +: 8] = X_TERM;
                    else begin
                        code = p[8 + 8 * k + (7 - k) + 7 * (i - k - 1) +: 7];
                        d[8 * i +: 8] = (code == 7'h00) ? X_IDLE : X_ERR;
                    end
                end
                c = 8'hFF << k;
            end
        end
        if (found) return {2'd0, c, d};
        if (t == 8'h2D || t == 8'h4B || t == 8'h55 || t == 8'h66) begin
            for (int i = 0; i < 8; i++) d[8 * i +: 8] = X_IDLE;
            return {2'd3, 8'hFF, d};
        end
        for (int i = 0; i < 8; i++) d[8 * i +: 8] = X_ERR;
        return {2'd2, 8'hFF, d};
    endfunction

    // ------------------------------------------------------------------------------------------------------ CRC-32
    // IEEE 802.3 (reflected, polynomial 04C11DB7), the register as in the usual serial implementation: start at FFFFFFFF, feed
    // n bytes (least significant bit first), send ~crc low byte first. The residue after a frame and its FCS is CRC_RESIDUE.
    function automatic logic [31:0] crc_upd(input logic [31:0] crc, input logic [63:0] d, input int n);
        logic [31:0] r; logic fb;
        r = crc;
        for (int i = 0; i < 8; i++) begin
            if (i < n) begin
                for (int b = 0; b < 8; b++) begin
                    fb = r[0] ^ d[8 * i + b];
                    r = {1'b0, r[31:1]};
                    if (fb) r = r ^ 32'hEDB88320;
                end
            end
        end
        return r;
    endfunction

    // the end of a frame: n data bytes (1..8) of d, then the 4 FCS bytes, the terminate and idles, as two XGMII words: {c[15:0], d[127:0]}
    function automatic logic [143:0] frame_end(input logic [63:0] d, input int n, input logic [31:0] fcs);
        logic [127:0] v, dx; logic [15:0] cv;
        v = {16{X_IDLE}}; cv = 16'hFFFF; dx = {64'd0, d};
        for (int i = 0; i < 16; i++) begin
            if (i < n) begin v[8 * i +: 8] = dx[8 * i +: 8]; cv[i] = 1'b0; end
            else if (i < n + 4) begin v[8 * i +: 8] = fcs[8 * (i - n) +: 8]; cv[i] = 1'b0; end
            else if (i == n + 4) begin v[8 * i +: 8] = X_TERM; cv[i] = 1'b1; end
        end
        return {cv, v};
    endfunction

    // a terminate character in the word: {found, lane[2:0]} (the control vector must be 1 from that lane up and 0 below it)
    function automatic logic [3:0] term_lane(input logic [63:0] d, input logic [7:0] c);
        logic [3:0] r; r = 4'd0;
        for (int k = 0; k < 8; k++) if (c == (8'hFF << k) && d[8 * k +: 8] == X_TERM) r = {1'b1, 3'(k)};
        return r;
    endfunction
endpackage
