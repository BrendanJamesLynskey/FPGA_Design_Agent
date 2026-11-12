// ipv4_udp_tx.sv: UDP over IPv4 transmit (RFC 768, RFC 791, RFC 1071) (ip_lib, brief 63D). Byte-wide AXI-Stream in
// (one UDP payload per frame, tlast on its last byte) and out (an Ethernet frame without the FCS; the MAC pads it).
//
// The payload is stored first (store and forward), so that its length and its UDP checksum are known before the
// headers leave. The destination (MAC, IPv4 address, ports) is taken from s_dst_* and s_*_port with the payload's
// first beat; the MAC address normally comes from the ARP cache (arp_responder) or, for a multicast group, from the
// group (01-00-5E and its low 23 bits; the caller's job).
// Frame: Ethernet II (destination, own_mac, 0x0800), IPv4 (version 4, IHL 5, DSCP/ECN 0, total length, an
// identification that counts datagrams, no fragmentation flags, TTL, protocol 17, header checksum, own_ip, the
// destination), UDP (ports, length, checksum), payload. CSUM = 1 computes the UDP checksum over the pseudo-header,
// header and payload (an all-zero result is sent as 0xFFFF, RFC 768); CSUM = 0 sends 0 (no checksum, allowed for
// IPv4). A payload longer than MAX_PAYLOAD is dropped whole (ev_too_long). RAM selects the buffer's memory, "bram"
// or "lutram" (the implementation variants; same function). One datagram at a time: s_axis is not ready while the
// previous one is being sent.

module ipv4_udp_tx #(
    parameter int MAX_PAYLOAD = 1472,   // bytes, 1..8972 (1472: a 1500-byte MTU; 8972: a 9000-byte MTU)
    parameter int CSUM        = 1,      // 1: compute the UDP checksum; 0: send 0
    parameter int TTL         = 64,     // 1..255
    parameter     RAM         = "bram"  // "bram" or "lutram"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [47:0] own_mac,
    input  logic [31:0] own_ip,
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic [47:0] s_dst_mac,      // taken with the first beat
    input  logic [31:0] s_dst_ip,
    input  logic [15:0] s_src_port,
    input  logic [15:0] s_dst_port,
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        ev_sent,        // a datagram's last byte left
    output logic        ev_too_long     // a payload over MAX_PAYLOAD was dropped
);
    localparam int AW = $clog2(MAX_PAYLOAD + 1);
    initial begin
        if (MAX_PAYLOAD < 1 || MAX_PAYLOAD > 8972) $error("ipv4_udp_tx: MAX_PAYLOAD must be in 1..8972 (got %0d)", MAX_PAYLOAD);
        if (CSUM != 0 && CSUM != 1) $error("ipv4_udp_tx: CSUM must be 0 or 1 (got %0d)", CSUM);
        if (TTL < 1 || TTL > 255) $error("ipv4_udp_tx: TTL must be in 1..255 (got %0d)", TTL);
        if (RAM != "bram" && RAM != "lutram") $error("ipv4_udp_tx: RAM must be \"bram\" or \"lutram\"");
    end
    function automatic logic [15:0] fold(input logic [31:0] s);
        logic [16:0] t;
        t = {1'b0, s[31:16]} + {1'b0, s[15:0]};
        return t[15:0] + {15'd0, t[16]};
    endfunction

    // ---------------------------------------------------------------- take the payload
    localparam logic [1:0] S_IN = 2'd0, S_CALC = 2'd1, S_OUT = 2'd2;
    logic [1:0]  st;
    logic [15:0] n;                     // payload bytes stored
    logic        over;                  // this payload is too long: drop it
    logic [31:0] p_acc;                 // sum of the payload as 16-bit words
    logic [47:0] d_mac;
    logic [31:0] d_ip;
    logic [15:0] sp, dp, ident;
    logic        beat;
    assign s_axis_tready = (st == S_IN);
    assign beat = s_axis_tvalid && s_axis_tready;
    logic we;
    assign we = beat && !over && n < 16'(MAX_PAYLOAD);

    // ---------------------------------------------------------------- headers
    logic [15:0] ulen, tlen, ipcs, ucs;
    assign ulen = n + 16'd8;
    assign tlen = n + 16'd28;
    logic [31:0] ip_sum, u_sum;
    assign ip_sum = 32'h4500 + {16'd0, tlen} + {16'd0, ident} + {16'd0, 8'(TTL), 8'd17} + {16'd0, own_ip[31:16]} +
                    {16'd0, own_ip[15:0]} + {16'd0, d_ip[31:16]} + {16'd0, d_ip[15:0]};
    assign u_sum  = p_acc + {16'd0, own_ip[31:16]} + {16'd0, own_ip[15:0]} + {16'd0, d_ip[31:16]} + {16'd0, d_ip[15:0]} +
                    32'd17 + {16'd0, ulen} + {16'd0, sp} + {16'd0, dp} + {16'd0, ulen};
    function automatic logic [7:0] hdr_byte(input logic [5:0] i, input logic [47:0] dm, input logic [47:0] sm,
                                            input logic [15:0] tl, input logic [15:0] id, input logic [15:0] ic,
                                            input logic [31:0] si, input logic [31:0] di, input logic [15:0] s_p,
                                            input logic [15:0] d_p, input logic [15:0] ul, input logic [15:0] uc);
        case (i)
            6'd0:  hdr_byte = dm[47:40]; 6'd1:  hdr_byte = dm[39:32]; 6'd2:  hdr_byte = dm[31:24];
            6'd3:  hdr_byte = dm[23:16]; 6'd4:  hdr_byte = dm[15:8];  6'd5:  hdr_byte = dm[7:0];
            6'd6:  hdr_byte = sm[47:40]; 6'd7:  hdr_byte = sm[39:32]; 6'd8:  hdr_byte = sm[31:24];
            6'd9:  hdr_byte = sm[23:16]; 6'd10: hdr_byte = sm[15:8];  6'd11: hdr_byte = sm[7:0];
            6'd12: hdr_byte = 8'h08;     6'd13: hdr_byte = 8'h00;     6'd14: hdr_byte = 8'h45;
            6'd15: hdr_byte = 8'h00;     6'd16: hdr_byte = tl[15:8];  6'd17: hdr_byte = tl[7:0];
            6'd18: hdr_byte = id[15:8];  6'd19: hdr_byte = id[7:0];   6'd20: hdr_byte = 8'h00;
            6'd21: hdr_byte = 8'h00;     6'd22: hdr_byte = 8'(TTL);   6'd23: hdr_byte = 8'd17;
            6'd24: hdr_byte = ic[15:8];  6'd25: hdr_byte = ic[7:0];
            6'd26: hdr_byte = si[31:24]; 6'd27: hdr_byte = si[23:16]; 6'd28: hdr_byte = si[15:8];
            6'd29: hdr_byte = si[7:0];   6'd30: hdr_byte = di[31:24]; 6'd31: hdr_byte = di[23:16];
            6'd32: hdr_byte = di[15:8];  6'd33: hdr_byte = di[7:0];
            6'd34: hdr_byte = s_p[15:8]; 6'd35: hdr_byte = s_p[7:0];  6'd36: hdr_byte = d_p[15:8];
            6'd37: hdr_byte = d_p[7:0];  6'd38: hdr_byte = ul[15:8];  6'd39: hdr_byte = ul[7:0];
            6'd40: hdr_byte = uc[15:8];  default: hdr_byte = uc[7:0];
        endcase
    endfunction

    // ---------------------------------------------------------------- buffer
    logic [AW-1:0] wa, ra;
    logic [7:0]    rq;
    logic          rd_en;
    assign wa = AW'(n);
    if (RAM == "lutram") begin : g_lutram
        (* ram_style = "distributed" *) logic [7:0] mem [MAX_PAYLOAD];
        always_ff @(posedge clk) begin
            if (we) mem[wa] <= s_axis_tdata;
            if (rd_en) rq <= mem[ra];
        end
    end else begin : g_bram
        (* ram_style = "block" *) logic [7:0] mem [MAX_PAYLOAD];
        always_ff @(posedge clk) begin
            if (we) mem[wa] <= s_axis_tdata;
            if (rd_en) rq <= mem[ra];
        end
    end

    // ---------------------------------------------------------------- send: 42 header bytes, then the payload
    logic [15:0] j, rj;                 // next frame byte; the byte now in the read stage
    logic        rv, take, more;
    assign take  = !m_axis_tvalid || m_axis_tready;
    assign more  = (st == S_OUT) && j < tlen + 16'd14;
    assign rd_en = more && (take || !rv);
    assign ra    = AW'(j - 16'd42);
    logic [7:0]  hb;
    assign hb = hdr_byte(rj[5:0], d_mac, own_mac, tlen, ident, ipcs, own_ip, d_ip, sp, dp, ulen, ucs);

    always_ff @(posedge clk) begin
        ev_sent <= 1'b0; ev_too_long <= 1'b0;
        if (rst) begin
            st <= S_IN; n <= '0; over <= 1'b0; p_acc <= '0; d_mac <= '0; d_ip <= '0; sp <= '0; dp <= '0; ident <= '0;
            ipcs <= '0; ucs <= '0; j <= '0; rj <= '0; rv <= 1'b0;
            m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0;
        end else begin
            case (st)
                S_IN: if (beat) begin
                    if (n == 16'd0 && !over) begin
                        d_mac <= s_dst_mac; d_ip <= s_dst_ip; sp <= s_src_port; dp <= s_dst_port;
                    end
                    if (n >= 16'(MAX_PAYLOAD)) over <= 1'b1;
                    else if (!over) begin
                        n <= n + 16'd1;
                        p_acc <= p_acc + 32'(n[0] ? {8'd0, s_axis_tdata} : {s_axis_tdata, 8'd0});
                    end
                    if (s_axis_tlast) begin
                        if (over || n >= 16'(MAX_PAYLOAD)) begin
                            ev_too_long <= 1'b1; over <= 1'b0; n <= '0; p_acc <= '0;
                        end else st <= S_CALC;
                    end
                end
                S_CALC: begin
                    ipcs <= ~fold(ip_sum);
                    ucs  <= (CSUM == 0) ? 16'h0000 : ((~fold(u_sum) == 16'h0000) ? 16'hFFFF : ~fold(u_sum));
                    st <= S_OUT; j <= '0; rv <= 1'b0;
                end
                default: ;                                  // S_OUT
            endcase
            if (take) begin
                m_axis_tvalid <= rv;
                m_axis_tdata  <= (rj < 16'd42) ? hb : rq;
                m_axis_tlast  <= rv && (rj == tlen + 16'd13);
                rv <= 1'b0;
            end
            if (rd_en) begin rv <= 1'b1; rj <= j; j <= j + 16'd1; end
            if (st == S_OUT && m_axis_tvalid && m_axis_tready && m_axis_tlast) begin
                st <= S_IN; n <= '0; p_acc <= '0; ident <= ident + 16'd1; ev_sent <= 1'b1;
            end
        end
    end
endmodule
