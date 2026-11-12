// arp_responder.sv: ARP for one IPv4 address (RFC 826) with a small cache and a requester for transmit next-hop
// lookups (ip_lib, brief 63D). Byte-wide AXI-Stream; frames are Ethernet frames without the FCS, as a MAC's receive
// stream gives them and its transmit stream takes them.
//
// Receive (s_axis, always ready): an ARP packet for Ethernet and IPv4 (EtherType 0x0806, hardware type 1, protocol
// type 0x0800, lengths 6 and 4, operation 1 or 2) in a frame of at least 42 bytes that ends without tuser.
//   - A request whose target protocol address is own_ip is answered: a reply to the sender's hardware address, own_mac
//     and own_ip as the sender, the requester as the target.
//   - The sender's mapping is learnt when the packet is addressed to own_ip (request or reply), and updated when the
//     sender is already in the cache (RFC 826's merge step). A sender address of 0.0.0.0 (an address probe) is never
//     learnt.
//   - One reply waits while another is being sent; a request that finds both busy is not answered (ev_drop).
// Cache: CACHE_N entries of {IPv4, MAC}, fully associative. A new entry takes a free slot, else the slots in turn
// (round robin). flush empties it. Entries do not age: flush them from outside when a timeout is needed.
// Lookup (lk_*): one lookup a clock; lk_done one clock later with lk_hit and lk_mac. On a miss the block sends an ARP
// request for lk_ip (broadcast) unless one is waiting, or one for the same address went out less than HOLDOFF clocks
// ago; the caller asks again later.
// Transmit (m_axis): 42-byte frames (the MAC pads them to the minimum), replies before requests.

module arp_responder #(
    parameter int CACHE_N = 4,          // cache entries, 1..16
    parameter int HOLDOFF = 1000        // clocks between two requests for the same address, 1..16777215
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [47:0] own_mac,        // first byte on the wire in [47:40]
    input  logic [31:0] own_ip,         // first byte on the wire in [31:24]
    // receive
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tuser,   // on tlast: the frame is bad
    // transmit
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    // next-hop lookup
    input  logic        lk_valid,
    input  logic [31:0] lk_ip,
    output logic        lk_ready,
    output logic        lk_done,
    output logic        lk_hit,
    output logic [47:0] lk_mac,
    input  logic        flush,
    // events (one clock each)
    output logic        ev_rx_request,  // a request for own_ip
    output logic        ev_rx_reply,    // a reply to own_ip
    output logic        ev_tx_reply,
    output logic        ev_tx_request,
    output logic        ev_learn,
    output logic        ev_drop
);
    initial begin
        if (CACHE_N < 1 || CACHE_N > 16) $error("arp_responder: CACHE_N must be in 1..16 (got %0d)", CACHE_N);
        if (HOLDOFF < 1 || HOLDOFF > 16777215) $error("arp_responder: HOLDOFF must be in 1..16777215 (got %0d)", HOLDOFF);
    end
    localparam int CW = (CACHE_N > 1) ? $clog2(CACHE_N) : 1;
    assign s_axis_tready = 1'b1;
    assign lk_ready      = 1'b1;

    // ---------------------------------------------------------------- receive: the fields by byte index
    logic [5:0]  k;                     // index of the next byte (saturates at 63)
    logic [15:0] et, htype, ptype, op;
    logic [7:0]  hlen, plen;
    logic [47:0] sha;
    logic [31:0] spa, tpa;
    logic        fin, fin_bad, fin_long;
    logic        beat;
    assign beat = s_axis_tvalid && s_axis_tready;
    always_ff @(posedge clk) begin
        fin <= 1'b0;
        if (rst) begin
            k <= '0; et <= '0; htype <= '0; ptype <= '0; op <= '0; hlen <= '0; plen <= '0; sha <= '0; spa <= '0;
            tpa <= '0; fin_bad <= 1'b0; fin_long <= 1'b0;
        end else if (beat) begin
            case (k)
                6'd12, 6'd13: et    <= {et[7:0], s_axis_tdata};
                6'd14, 6'd15: htype <= {htype[7:0], s_axis_tdata};
                6'd16, 6'd17: ptype <= {ptype[7:0], s_axis_tdata};
                6'd18:        hlen  <= s_axis_tdata;
                6'd19:        plen  <= s_axis_tdata;
                6'd20, 6'd21: op    <= {op[7:0], s_axis_tdata};
                default: ;
            endcase
            if (k >= 6'd22 && k <= 6'd27) sha <= {sha[39:0], s_axis_tdata};
            if (k >= 6'd28 && k <= 6'd31) spa <= {spa[23:0], s_axis_tdata};
            if (k >= 6'd38 && k <= 6'd41) tpa <= {tpa[23:0], s_axis_tdata};
            if (s_axis_tlast) begin
                k <= '0; fin <= 1'b1; fin_bad <= s_axis_tuser; fin_long <= (k >= 6'd41);
            end else if (k != 6'd63) k <= k + 6'd1;
        end
    end
    logic arp_ok, for_me, is_req, is_rep;
    assign arp_ok = !fin_bad && fin_long && et == 16'h0806 && htype == 16'h0001 && ptype == 16'h0800 &&
                    hlen == 8'd6 && plen == 8'd4 && (op == 16'h0001 || op == 16'h0002);
    assign for_me = arp_ok && tpa == own_ip;
    assign is_req = for_me && op == 16'h0001;
    assign is_rep = for_me && op == 16'h0002;

    // ---------------------------------------------------------------- cache
    logic          c_v   [CACHE_N];
    logic [31:0]   c_ip  [CACHE_N];
    logic [47:0]   c_mac [CACHE_N];
    logic [CW-1:0] rr;
    logic          known, have_free;
    logic [CW-1:0] known_i, free_i;
    always_comb begin
        known = 1'b0; known_i = '0; have_free = 1'b0; free_i = '0;
        for (int i = CACHE_N - 1; i >= 0; i--) begin
            if (c_v[i] && c_ip[i] == spa) begin known = 1'b1; known_i = CW'(i); end
            if (!c_v[i]) begin have_free = 1'b1; free_i = CW'(i); end
        end
    end
    logic learn;
    assign learn = fin && arp_ok && spa != 32'd0 && (for_me || known);
    always_ff @(posedge clk) begin
        ev_learn <= 1'b0;
        if (rst || flush) begin
            for (int i = 0; i < CACHE_N; i++) begin c_v[i] <= 1'b0; c_ip[i] <= '0; c_mac[i] <= '0; end
            rr <= '0;
        end else if (learn) begin
            ev_learn <= 1'b1;
            if (known) c_mac[known_i] <= sha;
            else if (have_free) begin c_v[free_i] <= 1'b1; c_ip[free_i] <= spa; c_mac[free_i] <= sha; end
            else begin
                c_ip[rr] <= spa; c_mac[rr] <= sha;
                rr <= (int'(rr) == CACHE_N - 1) ? '0 : rr + 1'b1;
            end
        end
    end

    // ---------------------------------------------------------------- lookup and request holdoff
    logic          lk_h;
    logic [47:0]   lk_m;
    always_comb begin
        lk_h = 1'b0; lk_m = '0;
        for (int i = CACHE_N - 1; i >= 0; i--) if (c_v[i] && c_ip[i] == lk_ip) begin lk_h = 1'b1; lk_m = c_mac[i]; end
    end
    logic        req_pend, rep_pend;
    logic [31:0] req_tpa;
    logic [47:0] rep_tha;
    logic [31:0] rep_tpa;
    logic [31:0] ho_ip;
    logic [23:0] ho_t;
    logic        ask;
    assign ask = lk_valid && !lk_h && !req_pend && !(ho_t != '0 && ho_ip == lk_ip);
    always_ff @(posedge clk) begin
        lk_done <= 1'b0;
        if (rst) begin lk_hit <= 1'b0; lk_mac <= '0; ho_t <= '0; ho_ip <= '0; end
        else begin
            if (ho_t != '0) ho_t <= ho_t - 24'd1;
            if (lk_valid) begin lk_done <= 1'b1; lk_hit <= lk_h; lk_mac <= lk_m; end
            if (ask) begin ho_ip <= lk_ip; ho_t <= 24'(HOLDOFF); end
        end
    end

    // ---------------------------------------------------------------- transmit
    logic        sending, cur_rep;
    logic [5:0]  j;
    logic [47:0] cur_da, cur_tha;
    logic [31:0] cur_tpa;
    function automatic logic [7:0] arp_byte(input logic [5:0] i, input logic rep, input logic [47:0] da,
                                            input logic [47:0] tha, input logic [31:0] tp, input logic [47:0] sm,
                                            input logic [31:0] sp);
        case (i)
            6'd0:  arp_byte = da[47:40];  6'd1:  arp_byte = da[39:32];  6'd2:  arp_byte = da[31:24];
            6'd3:  arp_byte = da[23:16];  6'd4:  arp_byte = da[15:8];   6'd5:  arp_byte = da[7:0];
            6'd6:  arp_byte = sm[47:40];  6'd7:  arp_byte = sm[39:32];  6'd8:  arp_byte = sm[31:24];
            6'd9:  arp_byte = sm[23:16];  6'd10: arp_byte = sm[15:8];   6'd11: arp_byte = sm[7:0];
            6'd12: arp_byte = 8'h08;      6'd13: arp_byte = 8'h06;      6'd14: arp_byte = 8'h00;
            6'd15: arp_byte = 8'h01;      6'd16: arp_byte = 8'h08;      6'd17: arp_byte = 8'h00;
            6'd18: arp_byte = 8'h06;      6'd19: arp_byte = 8'h04;      6'd20: arp_byte = 8'h00;
            6'd21: arp_byte = rep ? 8'h02 : 8'h01;
            6'd22: arp_byte = sm[47:40];  6'd23: arp_byte = sm[39:32];  6'd24: arp_byte = sm[31:24];
            6'd25: arp_byte = sm[23:16];  6'd26: arp_byte = sm[15:8];   6'd27: arp_byte = sm[7:0];
            6'd28: arp_byte = sp[31:24];  6'd29: arp_byte = sp[23:16];  6'd30: arp_byte = sp[15:8];
            6'd31: arp_byte = sp[7:0];
            6'd32: arp_byte = tha[47:40]; 6'd33: arp_byte = tha[39:32]; 6'd34: arp_byte = tha[31:24];
            6'd35: arp_byte = tha[23:16]; 6'd36: arp_byte = tha[15:8];  6'd37: arp_byte = tha[7:0];
            6'd38: arp_byte = tp[31:24];  6'd39: arp_byte = tp[23:16];  6'd40: arp_byte = tp[15:8];
            default: arp_byte = tp[7:0];
        endcase
    endfunction

    logic start_rep, start_req;
    assign start_rep = !sending && rep_pend;
    assign start_req = !sending && !rep_pend && req_pend;
    always_ff @(posedge clk) begin
        ev_rx_request <= 1'b0; ev_rx_reply <= 1'b0; ev_tx_reply <= 1'b0; ev_tx_request <= 1'b0; ev_drop <= 1'b0;
        if (rst) begin
            sending <= 1'b0; cur_rep <= 1'b0; j <= '0; cur_da <= '0; cur_tha <= '0; cur_tpa <= '0;
            m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0;
            req_pend <= 1'b0; rep_pend <= 1'b0; req_tpa <= '0; rep_tha <= '0; rep_tpa <= '0;
        end else begin
            // start a frame: the first byte now, the rest as the receiver takes them
            if (start_rep || start_req) begin
                sending <= 1'b1; cur_rep <= start_rep; j <= 6'd1;
                cur_da  <= start_rep ? rep_tha : 48'hFFFF_FFFF_FFFF;
                cur_tha <= start_rep ? rep_tha : 48'h0;
                cur_tpa <= start_rep ? rep_tpa : req_tpa;
                m_axis_tvalid <= 1'b1; m_axis_tlast <= 1'b0;
                m_axis_tdata  <= start_rep ? rep_tha[47:40] : 8'hFF;
                if (start_rep) rep_pend <= 1'b0; else req_pend <= 1'b0;
            end else if (m_axis_tvalid && m_axis_tready) begin
                if (m_axis_tlast) begin
                    m_axis_tvalid <= 1'b0; sending <= 1'b0;
                    if (cur_rep) ev_tx_reply <= 1'b1; else ev_tx_request <= 1'b1;
                end else begin
                    m_axis_tdata <= arp_byte(j, cur_rep, cur_da, cur_tha, cur_tpa, own_mac, own_ip);
                    m_axis_tlast <= (j == 6'd41);
                    j <= j + 6'd1;
                end
            end
            // a request for own_ip: queue the reply
            if (fin && is_req) begin
                ev_rx_request <= 1'b1;
                if (!rep_pend || start_rep) begin rep_pend <= 1'b1; rep_tha <= sha; rep_tpa <= spa; end
                else ev_drop <= 1'b1;
            end
            if (fin && is_rep) ev_rx_reply <= 1'b1;
            if (ask) begin req_pend <= 1'b1; req_tpa <= lk_ip; end
        end
    end
endmodule
