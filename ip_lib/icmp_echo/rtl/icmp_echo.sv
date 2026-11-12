// icmp_echo.sv: answers ICMP echo requests (ping) to one IPv4 address (RFC 792, RFC 1122 3.2.2.6) (ip_lib, brief 63D).
// Byte-wide AXI-Stream; frames are Ethernet frames without the FCS.
//
// Receive (s_axis, always ready): the frame is stored while its headers are checked. It is an echo request for us
// when: EtherType 0x0800; IPv4 with a 20-byte header (version 4, IHL 5: requests with IP options are not answered);
// the header checksum is right; it is not a fragment (MF = 0, offset 0); protocol 1; destination own_ip; ICMP type 8,
// code 0; the ICMP checksum over the ICMP message (the IP total length, not the Ethernet padding) is right; the frame
// holds the whole datagram, fits in BUF_BYTES and ends without tuser.
// Reply (m_axis): the same datagram with the Ethernet addresses swapped (destination: the request's source; source:
// own_mac), the IP addresses swapped, TTL set to TTL, ICMP type 0, and both checksums updated incrementally
// (RFC 1624 equation 3). Identifier, sequence number and data are echoed unchanged. Length: 14 + IP total length.
// One frame is held at a time: requests that arrive while a reply is waiting or being sent are not answered
// (ev_busy). RAM selects the buffer's memory, "bram" or "lutram" (the implementation variants; same function).

module icmp_echo #(
    parameter int BUF_BYTES = 2048,     // the longest frame answered, bytes without FCS: a power of two, 128..16384
    parameter int TTL       = 64,       // TTL of the replies, 1..255
    parameter     RAM       = "bram"    // "bram" or "lutram"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [47:0] own_mac,
    input  logic [31:0] own_ip,
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tuser,
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        ev_request,     // a request was accepted (a reply will follow)
    output logic        ev_reply,       // a reply's last byte left
    output logic        ev_busy,        // a request arrived while the buffer was in use
    output logic        ev_bad          // an echo request to own_ip failed a check (checksum, length, fragment)
);
    localparam int AW = $clog2(BUF_BYTES);
    initial begin
        if ((1 << AW) != BUF_BYTES || BUF_BYTES < 128 || BUF_BYTES > 16384) $error("icmp_echo: BUF_BYTES must be a power of two in 128..16384 (got %0d)", BUF_BYTES);
        if (TTL < 1 || TTL > 255) $error("icmp_echo: TTL must be in 1..255 (got %0d)", TTL);
        if (RAM != "bram" && RAM != "lutram") $error("icmp_echo: RAM must be \"bram\" or \"lutram\"");
    end
    assign s_axis_tready = 1'b1;

    function automatic logic [15:0] oc_add(input logic [15:0] a, input logic [15:0] b);   // ones' complement sum
        logic [16:0] s;
        s = {1'b0, a} + {1'b0, b};
        return s[15:0] + {15'd0, s[16]};
    endfunction
    function automatic logic [15:0] fold(input logic [31:0] s);
        logic [16:0] t;
        t = {1'b0, s[31:16]} + {1'b0, s[15:0]};
        return t[15:0] + {15'd0, t[16]};
    endfunction

    // ---------------------------------------------------------------- receive and check
    logic          busy;                // a reply is waiting or being sent
    logic          stored;              // this frame is being written to the buffer
    logic [15:0]   k;                   // index of the next byte (saturates)
    logic [47:0]   sa;
    logic [15:0]   et, tl, ff, isum_rx, csum_rx;
    logic [7:0]    vi, ttl_rx, proto, typ, code;
    logic [31:0]   dst;
    logic [31:0]   ip_acc, ic_acc;
    logic          fin, f_bad, f_store;
    logic [15:0]   f_len;
    logic          beat, first;
    logic [15:0]   wv;                  // this byte as its place in a 16-bit word
    assign beat  = s_axis_tvalid;
    assign first = (k == 16'd0);
    assign wv    = k[0] ? {8'd0, s_axis_tdata} : {s_axis_tdata, 8'd0};
    logic [16:0] tl14;                  // the datagram's end in the frame, without overflow
    assign tl14 = {1'b0, tl} + 17'd14;
    logic we;
    assign we = beat && (first ? !busy : stored) && k < 16'(BUF_BYTES);
    always_ff @(posedge clk) begin
        fin <= 1'b0;
        if (rst) begin
            k <= '0; stored <= 1'b0; sa <= '0; et <= '0; tl <= '0; ff <= '0; isum_rx <= '0; csum_rx <= '0; vi <= '0;
            ttl_rx <= '0; proto <= '0; typ <= '0; code <= '0; dst <= '0; ip_acc <= '0; ic_acc <= '0;
            f_bad <= 1'b0; f_store <= 1'b0; f_len <= '0;
        end else if (beat) begin
            if (first) begin stored <= !busy; ip_acc <= '0; ic_acc <= '0; end
            if (k >= 16'd6 && k <= 16'd11) sa <= {sa[39:0], s_axis_tdata};
            case (k)
                16'd12, 16'd13: et      <= {et[7:0], s_axis_tdata};
                16'd14:         vi      <= s_axis_tdata;
                16'd16, 16'd17: tl      <= {tl[7:0], s_axis_tdata};
                16'd20, 16'd21: ff      <= {ff[7:0], s_axis_tdata};
                16'd22:         ttl_rx  <= s_axis_tdata;
                16'd23:         proto   <= s_axis_tdata;
                16'd24, 16'd25: isum_rx <= {isum_rx[7:0], s_axis_tdata};
                16'd34:         typ     <= s_axis_tdata;
                16'd35:         code    <= s_axis_tdata;
                16'd36, 16'd37: csum_rx <= {csum_rx[7:0], s_axis_tdata};
                default: ;
            endcase
            if (k >= 16'd30 && k <= 16'd33) dst <= {dst[23:0], s_axis_tdata};
            if (k >= 16'd14 && k <= 16'd33) ip_acc <= ip_acc + 32'(wv);
            if (k >= 16'd34 && {1'b0, k} < tl14) ic_acc <= ic_acc + 32'(wv);
            if (s_axis_tlast) begin
                fin <= 1'b1; f_bad <= s_axis_tuser; f_len <= k + 16'd1; f_store <= first ? !busy : stored;
                k <= '0;
            end else if (k != 16'hFFFF) k <= k + 16'd1;
        end
    end
    logic echo_me, ok;
    assign echo_me = et == 16'h0800 && vi == 8'h45 && proto == 8'd1 && dst == own_ip && typ == 8'd8;
    assign ok = echo_me && !f_bad && code == 8'd0 && ff[13:0] == 14'd0 && fold(ip_acc) == 16'hFFFF &&
                fold(ic_acc) == 16'hFFFF && tl >= 16'd28 && {1'b0, f_len} >= tl14 && tl14 <= 17'(BUF_BYTES);

    // ---------------------------------------------------------------- buffer
    logic [AW-1:0] ra;
    logic [7:0]    rq;
    logic          rd_en;
    if (RAM == "lutram") begin : g_lutram
        (* ram_style = "distributed" *) logic [7:0] mem [BUF_BYTES];
        always_ff @(posedge clk) begin
            if (we) mem[k[AW-1:0]] <= s_axis_tdata;
            if (rd_en) rq <= mem[ra];
        end
    end else begin : g_bram
        (* ram_style = "block" *) logic [7:0] mem [BUF_BYTES];
        always_ff @(posedge clk) begin
            if (we) mem[k[AW-1:0]] <= s_axis_tdata;
            if (rd_en) rq <= mem[ra];
        end
    end

    // ---------------------------------------------------------------- reply
    logic [47:0] r_da;
    logic [15:0] r_isum, r_csum, r_len;
    logic        sending;
    logic [15:0] j, rj;                 // next byte to read; the byte in rq
    logic        rv;
    logic        take;
    assign take  = !m_axis_tvalid || m_axis_tready;
    assign rd_en = sending && (take || !rv);
    // read address: the IP source and destination swap places
    always_comb begin
        if (j >= 16'd26 && j <= 16'd29)      ra = AW'(j + 16'd4);
        else if (j >= 16'd30 && j <= 16'd33) ra = AW'(j - 16'd4);
        else                                 ra = AW'(j);
    end
    function automatic logic [7:0] out_byte(input logic [15:0] i, input logic [7:0] m, input logic [47:0] da,
                                            input logic [47:0] smac, input logic [15:0] is, input logic [15:0] cs);
        case (i)
            16'd0: out_byte = da[47:40];   16'd1: out_byte = da[39:32];   16'd2: out_byte = da[31:24];
            16'd3: out_byte = da[23:16];   16'd4: out_byte = da[15:8];    16'd5: out_byte = da[7:0];
            16'd6: out_byte = smac[47:40]; 16'd7: out_byte = smac[39:32]; 16'd8: out_byte = smac[31:24];
            16'd9: out_byte = smac[23:16]; 16'd10: out_byte = smac[15:8]; 16'd11: out_byte = smac[7:0];
            16'd22: out_byte = 8'(TTL);
            16'd24: out_byte = is[15:8];   16'd25: out_byte = is[7:0];
            16'd34: out_byte = 8'd0;
            16'd36: out_byte = cs[15:8];   16'd37: out_byte = cs[7:0];
            default: out_byte = m;
        endcase
    endfunction
    always_ff @(posedge clk) begin
        ev_request <= 1'b0; ev_reply <= 1'b0; ev_busy <= 1'b0; ev_bad <= 1'b0;
        if (rst) begin
            busy <= 1'b0; sending <= 1'b0; j <= '0; rj <= '0; rv <= 1'b0; r_da <= '0; r_isum <= '0; r_csum <= '0;
            r_len <= '0; m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0;
        end else begin
            if (fin && echo_me) begin
                if (!ok) ev_bad <= 1'b1;
                else if (!f_store) ev_busy <= 1'b1;
                else begin
                    ev_request <= 1'b1;
                    busy <= 1'b1; sending <= 1'b1; j <= '0; rv <= 1'b0; r_da <= sa; r_len <= 16'd14 + tl;
                    // RFC 1624 eqn 3: HC' = ~(~HC + ~m + m'), m the old 16-bit field, m' the new one
                    r_isum <= ~oc_add(oc_add(~isum_rx, ~{ttl_rx, proto}), {8'(TTL), proto});
                    r_csum <= ~oc_add(oc_add(~csum_rx, ~{typ, code}), {8'd0, code});
                end
            end
            if (take) begin
                m_axis_tvalid <= rv;
                m_axis_tdata  <= out_byte(rj, rq, r_da, own_mac, r_isum, r_csum);
                m_axis_tlast  <= rv && (rj == r_len - 16'd1);
                rv <= 1'b0;
            end
            if (rd_en) begin
                rv <= 1'b1; rj <= j; j <= j + 16'd1;
                if (j == r_len - 16'd1) sending <= 1'b0;
            end
            if (m_axis_tvalid && m_axis_tready && m_axis_tlast) begin busy <= 1'b0; ev_reply <= 1'b1; end
        end
    end
endmodule
