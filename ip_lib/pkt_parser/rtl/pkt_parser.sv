// pkt_parser.sv: streaming header parser, one byte a clock, no store-and-forward.
//
// Parses Ethernet II, up to MAX_VLAN tags (TPID 0x8100, 0x88A8 or 0x9100), IPv4 (RFC 791: version, IHL, header
// checksum, fragment fields, TTL, protocol, addresses; options skipped by IHL) and IPv6 (RFC 8200: next header, hop
// limit, addresses; extension headers are not walked), then the UDP (RFC 768) or TCP (RFC 793) ports.
//
// The packet passes through unchanged with one register of latency. Beside it, one parsed-header word per packet
// appears on m_hdr as soon as the last field it needs has gone past (the L4 destination port, the end of the IP
// header, or the EtherType for non-IP frames), or at tlast when the frame ends early (flag trunc). Header words
// leave in packet order. Fields the frame did not reach are zero.
//
// m_hdr_tdata layout (most significant first; flow/net/model.py HDR_FIELDS is the reference):
//   dmac 48, smac 48, tci0 16, tci1 16, etype 16, proto 8, ttl 8, src 128, dst 128, sport 16, dport 16,
//   l3off 8, l4off 8, flags 16
//   flags: [1:0] VLAN tags, [2] ipv4, [3] ipv6, [4] udp, [5] tcp, [6] l4 ports valid, [7] fragment,
//          [8] IHL < 5, [9] wrong IP version, [10] bad IPv4 header checksum, [11] truncated
// IPv4 addresses sit in the low 32 bits of src/dst. IPv4 fragments with a non-zero offset carry no ports.

module pkt_parser #(
    parameter int MAX_VLAN = 2               // tags parsed: 0, 1 or 2 (a further tag is left as the EtherType)
) (
    input  logic         clk,
    input  logic         rst,
    input  logic [7:0]   s_axis_tdata,
    input  logic         s_axis_tvalid,
    output logic         s_axis_tready,
    input  logic         s_axis_tlast,
    input  logic         s_axis_tuser,
    output logic [7:0]   m_axis_tdata,
    output logic         m_axis_tvalid,
    input  logic         m_axis_tready,
    output logic         m_axis_tlast,
    output logic         m_axis_tuser,
    output logic [479:0] m_hdr_tdata,
    output logic         m_hdr_tvalid,
    input  logic         m_hdr_tready
);
    initial begin
        if (MAX_VLAN < 0 || MAX_VLAN > 2) $error("pkt_parser: MAX_VLAN must be 0, 1 or 2 (got %0d)", MAX_VLAN);
    end

    // ---- the parsed fields of the current packet -------------------------------------------------------------
    logic [47:0]  dmac, smac;
    logic [15:0]  tci0, tci1, etype, sport, dport;
    logic [7:0]   proto, ttl, l3off, l4off;
    logic [127:0] src, dst;
    logic [1:0]   vlan_n;
    logic         f_v4, f_v6, f_udp, f_tcp, f_l4, f_frag, f_ihl, f_ver, f_csum, f_trunc;

    // ---- parse state -----------------------------------------------------------------------------------------
    logic [10:0]  pos;                       // byte index in the packet (saturates)
    logic [7:0]   type_pos, tci_pos;
    logic [7:0]   thi;                       // first byte of the type field
    logic         type_done;
    logic [1:0]   l3k;                       // 0 none, 1 IPv4, 2 IPv6
    logic         l3_act;                    // still reading the L3 header
    logic [7:0]   l3_start;
    logic [5:0]   hl;                        // IPv4 header length in bytes (IHL * 4)
    logic         l4_act;
    logic [7:0]   l4_start;
    logic [15:0]  csum;
    logic [7:0]   csum_hi;
    logic         mf;
    logic [4:0]   off_hi;
    logic         off_nz;
    logic         done;                      // the header word of this packet has been emitted
    logic         emit_q;                    // copy the fields to m_hdr (the clock after the last field)

    logic hdr_free, out_ok, acc;
    assign hdr_free      = !m_hdr_tvalid || m_hdr_tready;
    assign out_ok        = !m_axis_tvalid || m_axis_tready;
    assign s_axis_tready = out_ok && !(emit_q && !hdr_free);
    assign acc           = s_axis_tvalid && s_axis_tready;

    // combinational helpers for the byte being accepted
    logic [7:0]   b;
    logic [10:0]  r3, r4;                    // offsets into the L3 and L4 headers
    logic [15:0]  tword;
    logic         is_tpid;
    logic [16:0]  s17;
    logic [15:0]  csum_next;
    always_comb begin
        b       = s_axis_tdata;
        r3      = pos - {3'b000, l3_start};
        r4      = pos - {3'b000, l4_start};
        tword   = {thi, b};
        is_tpid = (tword == 16'h8100) || (tword == 16'h88A8) || (tword == 16'h9100);
        s17     = {1'b0, csum} + {1'b0, csum_hi, b};
        csum_next = s17[15:0] + {15'd0, s17[16]};
    end

    // emit at this byte (the last needed field is in it)
    logic emit_now;

    always_ff @(posedge clk) begin
        if (rst) begin
            m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0; m_axis_tuser <= 1'b0;
            m_hdr_tvalid <= 1'b0; m_hdr_tdata <= '0;
            pos <= '0; emit_q <= 1'b0; done <= 1'b0;
            type_pos <= 8'd12; tci_pos <= '0; thi <= '0; type_done <= 1'b0; l3k <= '0; l3_act <= 1'b0;
            l3_start <= '0; hl <= '0; l4_act <= 1'b0; l4_start <= '0; csum <= '0; csum_hi <= '0; mf <= 1'b0;
            off_hi <= '0; off_nz <= 1'b0;
            dmac <= '0; smac <= '0; tci0 <= '0; tci1 <= '0; etype <= '0; sport <= '0; dport <= '0; proto <= '0;
            ttl <= '0; l3off <= '0; l4off <= '0; src <= '0; dst <= '0; vlan_n <= '0;
            {f_v4, f_v6, f_udp, f_tcp, f_l4, f_frag, f_ihl, f_ver, f_csum, f_trunc} <= '0;
        end else begin
            // ---- output stream register ----
            if (acc) begin
                m_axis_tvalid <= 1'b1; m_axis_tdata <= b; m_axis_tlast <= s_axis_tlast; m_axis_tuser <= s_axis_tuser;
            end else if (m_axis_tready) begin
                m_axis_tvalid <= 1'b0;
            end
            // ---- header word ----
            if (m_hdr_tready) m_hdr_tvalid <= 1'b0;
            if (emit_q && hdr_free) begin
                m_hdr_tvalid <= 1'b1;
                m_hdr_tdata  <= {dmac, smac, tci0, tci1, etype, proto, ttl, src, dst, sport, dport, l3off, l4off,
                                 4'b0000, f_trunc, f_csum, f_ver, f_ihl, f_frag, f_l4, f_tcp, f_udp, f_v6, f_v4,
                                 vlan_n};
                emit_q <= 1'b0;
            end
            // ---- parse the accepted byte ----
            if (acc) begin
                emit_now = 1'b0;
                if (pos == 11'd0) begin
                    // a new packet: clear the previous one's fields (m_hdr took its copy before this edge)
                    smac <= '0; tci0 <= '0; tci1 <= '0; etype <= '0; sport <= '0; dport <= '0; proto <= '0;
                    ttl <= '0; l3off <= '0; l4off <= '0; src <= '0; dst <= '0; vlan_n <= '0;
                    {f_v4, f_v6, f_udp, f_tcp, f_l4, f_frag, f_ihl, f_ver, f_csum, f_trunc} <= '0;
                    type_pos <= 8'd12; type_done <= 1'b0; l3k <= '0; l3_act <= 1'b0; l4_act <= 1'b0;
                    done <= 1'b0; csum <= '0; mf <= 1'b0; off_hi <= '0; off_nz <= 1'b0; dmac <= {b, 40'd0};
                end
                if (!done || pos == 11'd0) begin
                    // Ethernet addresses
                    if (pos > 11'd0 && pos < 11'd6) dmac[8 * (5 - pos[2:0]) +: 8] <= b;
                    if (pos >= 11'd6 && pos < 11'd12) smac[8 * (11 - pos[3:0]) +: 8] <= b;
                    // type field and VLAN tags
                    if (!type_done && pos == {3'b000, type_pos}) thi <= b;
                    if (!type_done && pos == {3'b000, type_pos} + 11'd1) begin
                        if (is_tpid && vlan_n < 2'(MAX_VLAN)) begin
                            vlan_n   <= vlan_n + 2'd1;
                            tci_pos  <= type_pos + 8'd2;
                            type_pos <= type_pos + 8'd4;
                        end else begin
                            etype     <= tword;
                            type_done <= 1'b1;
                            l3_start  <= type_pos + 8'd2;
                            l3off     <= type_pos + 8'd2;
                            if (tword == 16'h0800)      begin l3k <= 2'd1; l3_act <= 1'b1; f_v4 <= 1'b1; end
                            else if (tword == 16'h86DD) begin l3k <= 2'd2; l3_act <= 1'b1; f_v6 <= 1'b1; end
                            else emit_now = 1'b1;
                        end
                    end
                    if (!type_done && vlan_n != 2'd0 && pos == {3'b000, tci_pos}) begin
                        if (vlan_n == 2'd1) tci0[15:8] <= b; else tci1[15:8] <= b;
                    end
                    if (!type_done && vlan_n != 2'd0 && pos == {3'b000, tci_pos} + 11'd1) begin
                        if (vlan_n == 2'd1) tci0[7:0] <= b; else tci1[7:0] <= b;
                    end
                    // IPv4
                    if (type_done && l3_act && l3k == 2'd1) begin
                        if (r3 == 11'd0) begin
                            csum_hi <= b;
                            if (b[7:4] != 4'd4)     begin f_ver <= 1'b1; l3_act <= 1'b0; emit_now = 1'b1; end
                            else if (b[3:0] < 4'd5) begin f_ihl <= 1'b1; l3_act <= 1'b0; emit_now = 1'b1; end
                            else hl <= {b[3:0], 2'b00};
                        end else begin
                            if (r3[0] == 1'b0) csum_hi <= b;
                            else               csum    <= csum_next;
                            case (r3)
                                11'd6:  begin mf <= b[5]; off_hi <= b[4:0]; end
                                11'd7:  begin off_nz <= ({off_hi, b} != 13'd0); f_frag <= mf || ({off_hi, b} != 13'd0); end
                                11'd8:  ttl <= b;
                                11'd9:  proto <= b;
                                default: ;
                            endcase
                            if (r3 >= 11'd12 && r3 < 11'd16) src[8 * (15 - r3[3:0]) +: 8] <= b;
                            if (r3 >= 11'd16 && r3 < 11'd20) dst[8 * (19 - r3[4:0]) +: 8] <= b;
                            if (r3 == {5'd0, hl} - 11'd1) begin
                                l3_act <= 1'b0;
                                f_csum <= (csum_next != 16'hFFFF);
                                if ((proto == 8'd6 || proto == 8'd17) && !off_nz) begin
                                    l4_act <= 1'b1; l4_start <= pos[7:0] + 8'd1; l4off <= pos[7:0] + 8'd1;
                                    f_udp <= (proto == 8'd17); f_tcp <= (proto == 8'd6);
                                end else emit_now = 1'b1;
                            end
                        end
                    end
                    // IPv6
                    if (type_done && l3_act && l3k == 2'd2) begin
                        if (r3 == 11'd0 && b[7:4] != 4'd6) begin f_ver <= 1'b1; l3_act <= 1'b0; emit_now = 1'b1; end
                        if (r3 == 11'd6) proto <= b;
                        if (r3 == 11'd7) ttl <= b;
                        if (r3 >= 11'd8 && r3 < 11'd24)  src[8 * (23 - r3[4:0]) +: 8] <= b;
                        if (r3 >= 11'd24 && r3 < 11'd40) dst[8 * (39 - r3[5:0]) +: 8] <= b;
                        if (r3 == 11'd39) begin
                            l3_act <= 1'b0;
                            if (proto == 8'd6 || proto == 8'd17) begin
                                l4_act <= 1'b1; l4_start <= pos[7:0] + 8'd1; l4off <= pos[7:0] + 8'd1;
                                f_udp <= (proto == 8'd17); f_tcp <= (proto == 8'd6);
                            end else emit_now = 1'b1;
                        end
                    end
                    // L4 ports
                    if (l4_act) begin
                        case (r4)
                            11'd0: sport[15:8] <= b;
                            11'd1: sport[7:0]  <= b;
                            11'd2: dport[15:8] <= b;
                            11'd3: begin dport[7:0] <= b; f_l4 <= 1'b1; l4_act <= 1'b0; emit_now = 1'b1; end
                            default: ;
                        endcase
                    end
                    if (s_axis_tlast && !emit_now) f_trunc <= 1'b1;
                    if (emit_now || s_axis_tlast) begin done <= 1'b1; emit_q <= 1'b1; end
                end
                pos <= s_axis_tlast ? 11'd0 : (pos == 11'h7FF ? pos : pos + 11'd1);
            end
        end
    end
endmodule
