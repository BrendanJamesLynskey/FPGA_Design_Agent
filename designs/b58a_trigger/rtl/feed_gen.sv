// feed_gen.sv: an in-FPGA source of mock market data (Bench Feed v1) for the second PL port, so a cable between the
// two ports closes a bench loop with both ends timed by one counter.
//
// Every `interval` clocks (while enabled, `npkts` packets, 0 = without end) it starts a UDP packet of `nmsg`
// messages. Message fields are pseudo-random (a 32-bit LFSR, seed fixed at reset): type ADD/MODIFY/CANCEL/TRADE,
// side, instrument (& inst_mask), price base_px + (random & px_mask), size 1..256, reference = the message's
// sequence number. These are stimulus values only; they model nothing real.
// Faults on request: every bad_every-th packet leaves with a bad FCS; every gap_every-th packet skips a sequence
// number. The MAC's data provider is registered, like order_ctl's.

module feed_gen (
    input  logic        clk,
    input  logic        rst,
    input  logic        en,
    input  logic [31:0] interval,
    input  logic [31:0] npkts,
    input  logic [7:0]  nmsg,           // 1..91
    input  logic [15:0] inst_mask,
    input  logic [31:0] base_px,
    input  logic [31:0] px_mask,
    input  logic [15:0] bad_every,
    input  logic [15:0] gap_every,
    input  logic [47:0] src_mac,
    input  logic [47:0] dst_mac,
    input  logic [31:0] src_ip,
    input  logic [31:0] dst_ip,
    input  logic [15:0] src_port,
    input  logic [15:0] dst_port,
    output logic [31:0] sent,           // packets started
    // to mac_tx
    output logic        tx_start,
    output logic [10:0] tx_len,
    input  logic        tx_ready,
    input  logic        tx_req_valid,
    input  logic [10:0] tx_req_idx,
    output logic [7:0]  tx_data,
    output logic        tx_last_byte,
    output logic        tx_poison
);
    logic [31:0] t, lfsr, seq_next, seq_cur;
    logic [15:0] bad_c, gap_c;
    logic        bad_cur;
    logic [7:0]  n;
    logic [15:0] ulen, tlen;
    logic [15:0] csum;
    logic        active;                // a packet is being sent

    // message fields
    logic [7:0]  m_ty;
    logic        m_sd;
    logic [15:0] m_in;
    logic [31:0] m_px, m_sz, m_rf;
    logic [7:0]  nx_ty;
    logic        nx_sd;
    logic [15:0] nx_in;
    logic [31:0] nx_px, nx_sz, l1, l2;
    function automatic logic [31:0] step(input logic [31:0] x);
        return x[0] ? ((x >> 1) ^ 32'hA300_0001) : (x >> 1);   // Galois, taps 32, 30, 26, 25
    endfunction
    always_comb begin
        l1 = step(lfsr);
        l2 = step(l1);
        nx_ty = {6'd0, l1[1:0]} + 8'd1;
        nx_sd = l1[2];
        nx_in = l1[18:3] & inst_mask;
        nx_px = base_px + (l2 & px_mask);
        nx_sz = {24'd0, l2[31:24]} + 32'd1;
    end

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

    logic [10:0] fi;
    logic [10:0] po;                    // offset in the message area
    logic [3:0]  mo;
    logic [7:0]  mk;
    assign fi = tx_req_idx;
    assign po = fi - 11'd50;
    assign mo = po[3:0];
    assign mk = {1'b0, po[10:4]};
    logic [7:0] fb;
    logic       newmsg;
    assign newmsg = tx_req_valid && fi >= 11'd50 && mo == 4'd0;
    always_comb begin
        logic [7:0]  ty;
        logic        sd;
        logic [15:0] in;
        logic [31:0] px, sz, rf;
        ty = newmsg ? nx_ty : m_ty;
        sd = newmsg ? nx_sd : m_sd;
        in = newmsg ? nx_in : m_in;
        px = newmsg ? nx_px : m_px;
        sz = newmsg ? nx_sz : m_sz;
        rf = newmsg ? seq_cur + {24'd0, mk} : m_rf;
        fb = 8'h00;
        if (fi <= 11'd5)       fb = b48(dst_mac, 3'(fi));
        else if (fi <= 11'd11) fb = b48(src_mac, 3'(fi - 11'd6));
        else if (fi < 11'd50) begin
            case (fi)
                11'd12: fb = 8'h08; 11'd13: fb = 8'h00;
                11'd14: fb = 8'h45; 11'd15: fb = 8'h00; 11'd16: fb = tlen[15:8]; 11'd17: fb = tlen[7:0];
                11'd18: fb = 8'h00; 11'd19: fb = 8'h00; 11'd20: fb = 8'h40; 11'd21: fb = 8'h00;
                11'd22: fb = 8'd64; 11'd23: fb = 8'd17; 11'd24: fb = csum[15:8]; 11'd25: fb = csum[7:0];
                11'd34: fb = src_port[15:8]; 11'd35: fb = src_port[7:0];
                11'd36: fb = dst_port[15:8]; 11'd37: fb = dst_port[7:0];
                11'd38: fb = ulen[15:8]; 11'd39: fb = ulen[7:0]; 11'd40: fb = 8'h00; 11'd41: fb = 8'h00;
                11'd42: fb = 8'h42; 11'd43: fb = 8'h46; 11'd44: fb = 8'h01; 11'd45: fb = n;
                default: begin
                    if (fi >= 11'd26 && fi <= 11'd29)      fb = b32(src_ip, 2'(fi - 11'd26));
                    else if (fi >= 11'd30 && fi <= 11'd33) fb = b32(dst_ip, 2'(fi - 11'd30));
                    else if (fi >= 11'd46 && fi <= 11'd49) fb = b32(seq_cur, 2'(fi - 11'd46));
                end
            endcase
        end else begin
            case (mo)
                4'd0: fb = ty;
                4'd1: fb = {7'd0, sd};
                4'd2: fb = in[15:8];
                4'd3: fb = in[7:0];
                4'd4, 4'd5, 4'd6, 4'd7:     fb = b32(px, 2'(mo - 4'd4));
                4'd8, 4'd9, 4'd10, 4'd11:   fb = b32(sz, 2'(mo - 4'd8));
                default:                    fb = b32(rf, 2'(mo - 4'd12));
            endcase
        end
    end

    function automatic logic [15:0] ip_csum(input logic [31:0] sip, input logic [31:0] dip, input logic [15:0] tl);
        logic [31:0] s;
        s = 32'h4500 + {16'h0, tl} + 32'h4000 + 32'h4011
            + {16'h0, sip[31:16]} + {16'h0, sip[15:0]} + {16'h0, dip[31:16]} + {16'h0, dip[15:0]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        s = {16'h0, s[15:0]} + {16'h0, s[31:16]};
        return ~s[15:0];
    endfunction

    logic [7:0] nn;
    assign nn = (nmsg == 0) ? 8'd1 : (nmsg > 8'd91 ? 8'd91 : nmsg);

    always_ff @(posedge clk) begin
        tx_start <= 1'b0;
        if (rst) begin
            t <= '0; lfsr <= 32'h1234_5678; seq_next <= 32'd1; seq_cur <= '0; bad_c <= '0; gap_c <= '0;
            bad_cur <= 1'b0; n <= 8'd1; ulen <= '0; tlen <= '0; csum <= '0; active <= 1'b0; sent <= '0;
            m_ty <= '0; m_sd <= 1'b0; m_in <= '0; m_px <= '0; m_sz <= '0; m_rf <= '0; tx_len <= '0; tx_data <= '0; tx_last_byte <= 1'b0;
        end else begin
            tx_data <= fb;
            tx_last_byte <= (tx_req_idx + 11'd1 == tx_len);
            if (newmsg) begin
                m_ty <= nx_ty; m_sd <= nx_sd; m_in <= nx_in; m_px <= nx_px; m_sz <= nx_sz;
                m_rf <= seq_cur + {24'd0, mk};
                lfsr <= l2;
            end
            if (!en) t <= '0;
            else if (t != 32'hFFFF_FFFF) t <= t + 32'd1;
            if (active && tx_ready && !tx_start) active <= 1'b0;
            if (en && !active && tx_ready && t + 32'd1 >= interval && (npkts == 0 || sent < npkts)) begin
                t <= '0;
                active <= 1'b1;
                tx_start <= 1'b1;
                n <= nn;
                ulen <= 16'd16 + {4'd0, nn, 4'd0};
                tlen <= 16'd36 + {4'd0, nn, 4'd0};
                csum <= ip_csum(src_ip, dst_ip, 16'd36 + {4'd0, nn, 4'd0});
                tx_len <= 11'd50 + {nn[6:0], 4'd0};
                sent <= sent + 32'd1;
                seq_cur <= seq_next;
                if (gap_every != 0 && gap_c + 16'd1 == gap_every) begin
                    gap_c <= '0; seq_next <= seq_next + {24'd0, nn} + 32'd1;
                end else begin
                    gap_c <= gap_c + 16'd1; seq_next <= seq_next + {24'd0, nn};
                end
                if (bad_every != 0 && bad_c + 16'd1 == bad_every) begin bad_c <= '0; bad_cur <= 1'b1; end
                else begin bad_c <= bad_c + 16'd1; bad_cur <= 1'b0; end
            end
        end
    end
    assign tx_poison = bad_cur && active;
endmodule
