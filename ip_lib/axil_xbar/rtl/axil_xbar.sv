// axil_xbar.sv: AXI4-Lite crossbar, N_M masters to N_S slaves (brief 65A).
//
// Each slave has its own write arbiter and its own read arbiter (round robin), so a write and a read, or transfers
// from different masters to different slaves, proceed at the same time. Each master has at most one write and one
// read in flight; the next is accepted after the previous response has been handed back, so responses return in
// order without IDs. Addresses outside every slave's range are answered by the crossbar itself with DECERR (and
// read data 0), without touching any slave.
//
// Address map: slave s owns the 2**S_BITS[s] bytes from S_BASE[s] (S_BASE[s] a multiple of the size). The block
// design generator (flow/blockdesign) assigns the map and checks it; the elaboration guards below refuse a
// misaligned or overlapping map as well.
//
// Timing, per transfer: write accepted (AWREADY and WREADY together) in the cycle both AWVALID and WVALID are seen
// and the target is free; forwarded from the next cycle; the slave's B is registered and handed back one cycle after
// it arrives. Reads alike. Uncontended, a write to a slave that answers at once takes 4 cycles from AWVALID/WVALID to
// BVALID at the master. The crossbar waits for both AWVALID and WVALID before it accepts a write (allowed by
// IHI 0022H A3.3.1); it never waits for a READY before raising a VALID.
//
// Reset: rst, active high, synchronous (like the rest of ip_lib); every VALID is low while rst is high.
module axil_xbar #(
    parameter int N_M    = 1,                         // masters (1..16)
    parameter int N_S    = 1,                         // slaves (1..32); the generator sets the map
    parameter int ADDR_W = 32,                        // address bits (12..64)
    parameter logic [N_S*ADDR_W-1:0] S_BASE = '0,     // slave s base address at [s*ADDR_W +: ADDR_W]
    parameter logic [N_S*8-1:0]      S_BITS = {N_S{8'd12}}   // slave s range is 2**S_BITS[s*8 +: 8] bytes (2..ADDR_W)
) (
    input  logic                  clk,
    input  logic                  rst,
    // slave ports of the crossbar: one per master, master m at [m*W +: W]
    input  logic [N_M*ADDR_W-1:0] s_axil_awaddr,
    input  logic [N_M*3-1:0]      s_axil_awprot,
    input  logic [N_M-1:0]        s_axil_awvalid,
    output logic [N_M-1:0]        s_axil_awready,
    input  logic [N_M*32-1:0]     s_axil_wdata,
    input  logic [N_M*4-1:0]      s_axil_wstrb,
    input  logic [N_M-1:0]        s_axil_wvalid,
    output logic [N_M-1:0]        s_axil_wready,
    output logic [N_M*2-1:0]      s_axil_bresp,
    output logic [N_M-1:0]        s_axil_bvalid,
    input  logic [N_M-1:0]        s_axil_bready,
    input  logic [N_M*ADDR_W-1:0] s_axil_araddr,
    input  logic [N_M*3-1:0]      s_axil_arprot,
    input  logic [N_M-1:0]        s_axil_arvalid,
    output logic [N_M-1:0]        s_axil_arready,
    output logic [N_M*32-1:0]     s_axil_rdata,
    output logic [N_M*2-1:0]      s_axil_rresp,
    output logic [N_M-1:0]        s_axil_rvalid,
    input  logic [N_M-1:0]        s_axil_rready,
    // master ports of the crossbar: one per slave, slave s at [s*W +: W]
    output logic [N_S*ADDR_W-1:0] m_axil_awaddr,
    output logic [N_S*3-1:0]      m_axil_awprot,
    output logic [N_S-1:0]        m_axil_awvalid,
    input  logic [N_S-1:0]        m_axil_awready,
    output logic [N_S*32-1:0]     m_axil_wdata,
    output logic [N_S*4-1:0]      m_axil_wstrb,
    output logic [N_S-1:0]        m_axil_wvalid,
    input  logic [N_S-1:0]        m_axil_wready,
    input  logic [N_S*2-1:0]      m_axil_bresp,
    input  logic [N_S-1:0]        m_axil_bvalid,
    output logic [N_S-1:0]        m_axil_bready,
    output logic [N_S*ADDR_W-1:0] m_axil_araddr,
    output logic [N_S*3-1:0]      m_axil_arprot,
    output logic [N_S-1:0]        m_axil_arvalid,
    input  logic [N_S-1:0]        m_axil_arready,
    input  logic [N_S*32-1:0]     m_axil_rdata,
    input  logic [N_S*2-1:0]      m_axil_rresp,
    input  logic [N_S-1:0]        m_axil_rvalid,
    output logic [N_S-1:0]        m_axil_rready
);
    localparam int MW = (N_M > 1) ? $clog2(N_M) : 1;    // master index bits
    localparam int TW = $clog2(N_S + 1);                // target index bits; N_S means "no slave" (DECERR)
    localparam logic [1:0] ST_IDLE = 2'd0, ST_FWD = 2'd1, ST_RESP = 2'd2;
    localparam logic [1:0] DECERR = 2'b11;

    // ---------------------------------------------------------------- elaboration guards
    initial begin
        if (N_M < 1 || N_M > 16) $error("axil_xbar: N_M %0d outside 1..16", N_M);
        if (N_S < 1 || N_S > 32) $error("axil_xbar: N_S %0d outside 1..32", N_S);
        if (ADDR_W < 12 || ADDR_W > 64) $error("axil_xbar: ADDR_W %0d outside 12..64", ADDR_W);
        for (int s = 0; s < N_S; s++) begin
            if (int'(S_BITS[s*8 +: 8]) < 2 || int'(S_BITS[s*8 +: 8]) > ADDR_W)
                $error("axil_xbar: S_BITS of slave %0d is %0d, outside 2..ADDR_W", s, S_BITS[s*8 +: 8]);
            else if ((S_BASE[s*ADDR_W +: ADDR_W] & ~({ADDR_W{1'b1}} << S_BITS[s*8 +: 8])) != '0)
                $error("axil_xbar: slave %0d base is not a multiple of its size", s);
        end
    end

    function automatic logic [ADDR_W-1:0] mask_of(input int s);
        mask_of = {ADDR_W{1'b1}} << S_BITS[s*8 +: 8];
    endfunction

    for (genvar ga = 1; ga < N_S; ga++) begin : g_overlap      // two ranges overlap when the larger one holds the other's base
        for (genvar gb = 0; gb < ga; gb++) begin : g_pair
            localparam int BA = int'(S_BITS[ga*8 +: 8]);
            localparam int BB = int'(S_BITS[gb*8 +: 8]);
            localparam logic [ADDR_W-1:0] MK = {ADDR_W{1'b1}} << ((BA > BB) ? BA : BB);
            initial if (((S_BASE[ga*ADDR_W +: ADDR_W] ^ S_BASE[gb*ADDR_W +: ADDR_W]) & MK) == '0)
                $error("axil_xbar: slaves %0d and %0d overlap", gb, ga);
        end
    end

    function automatic logic [TW-1:0] decode(input logic [ADDR_W-1:0] a);
        decode = TW'(N_S);
        for (int s = 0; s < N_S; s++)
            if (((a ^ S_BASE[s*ADDR_W +: ADDR_W]) & mask_of(s)) == '0) decode = TW'(s);
    endfunction

    // ---------------------------------------------------------------- per-master state
    logic [1:0]        w_st [N_M];
    logic [ADDR_W-1:0] w_addr [N_M];
    logic [2:0]        w_prot [N_M];
    logic [31:0]       w_data [N_M];
    logic [3:0]        w_strb [N_M];
    logic              w_awdone [N_M], w_wdone [N_M];
    logic [1:0]        w_resp [N_M];
    logic [1:0]        r_st [N_M];
    logic [ADDR_W-1:0] r_addr [N_M];
    logic [2:0]        r_prot [N_M];
    logic              r_ardone [N_M];
    logic [31:0]       r_data [N_M];
    logic [1:0]        r_resp [N_M];
    // ---------------------------------------------------------------- per-slave state
    logic              ws_busy [N_S], rs_busy [N_S];
    logic [MW-1:0]     ws_own [N_S], rs_own [N_S];       // the master that owns the slave's write / read side
    logic [MW-1:0]     ws_rr [N_S], rs_rr [N_S];         // the master granted last (round robin)

    // ---------------------------------------------------------------- requests and grants
    logic [TW-1:0] w_dec [N_M], r_dec [N_M];
    logic [N_M-1:0] w_req, r_req, w_gnt, r_gnt;
    logic          ws_g [N_S], rs_g [N_S];               // slave s grants this cycle ...
    logic [MW-1:0] ws_gm [N_S], rs_gm [N_S];             // ... to this master

    always_comb begin
        for (int m = 0; m < N_M; m++) begin
            w_dec[m] = decode(s_axil_awaddr[m*ADDR_W +: ADDR_W]);
            r_dec[m] = decode(s_axil_araddr[m*ADDR_W +: ADDR_W]);
            w_req[m] = (w_st[m] == ST_IDLE) && s_axil_awvalid[m] && s_axil_wvalid[m];
            r_req[m] = (r_st[m] == ST_IDLE) && s_axil_arvalid[m];
        end
        for (int s = 0; s < N_S; s++) begin
            ws_g[s] = 1'b0; ws_gm[s] = '0;
            rs_g[s] = 1'b0; rs_gm[s] = '0;
            for (int i = 1; i <= N_M; i++) begin          // round robin: start after the last grant
                int k;
                k = int'(ws_rr[s]) + i; if (k >= N_M) k = k - N_M;
                if (!ws_g[s] && !ws_busy[s] && w_req[k] && w_dec[k] == TW'(s)) begin ws_g[s] = 1'b1; ws_gm[s] = MW'(k); end
                k = int'(rs_rr[s]) + i; if (k >= N_M) k = k - N_M;
                if (!rs_g[s] && !rs_busy[s] && r_req[k] && r_dec[k] == TW'(s)) begin rs_g[s] = 1'b1; rs_gm[s] = MW'(k); end
            end
        end
        for (int m = 0; m < N_M; m++) begin               // a request with no slave is granted at once (DECERR)
            w_gnt[m] = w_req[m] && w_dec[m] == TW'(N_S);
            r_gnt[m] = r_req[m] && r_dec[m] == TW'(N_S);
        end
        for (int s = 0; s < N_S; s++) begin
            if (ws_g[s]) w_gnt[ws_gm[s]] = 1'b1;
            if (rs_g[s]) r_gnt[rs_gm[s]] = 1'b1;
        end
    end

    // ---------------------------------------------------------------- master-side outputs
    always_comb begin
        for (int m = 0; m < N_M; m++) begin
            s_axil_awready[m]        = w_gnt[m];
            s_axil_wready[m]         = w_gnt[m];
            s_axil_bvalid[m]         = (w_st[m] == ST_RESP);
            s_axil_bresp[m*2 +: 2]   = w_resp[m];
            s_axil_arready[m]        = r_gnt[m];
            s_axil_rvalid[m]         = (r_st[m] == ST_RESP);
            s_axil_rresp[m*2 +: 2]   = r_resp[m];
            s_axil_rdata[m*32 +: 32] = r_data[m];
        end
    end

    // ---------------------------------------------------------------- slave-side outputs (from the owning master)
    always_comb begin
        for (int s = 0; s < N_S; s++) begin
            m_axil_awaddr[s*ADDR_W +: ADDR_W] = w_addr[ws_own[s]];
            m_axil_awprot[s*3 +: 3]           = w_prot[ws_own[s]];
            m_axil_wdata[s*32 +: 32]          = w_data[ws_own[s]];
            m_axil_wstrb[s*4 +: 4]            = w_strb[ws_own[s]];
            m_axil_awvalid[s] = ws_busy[s] && !w_awdone[ws_own[s]];
            m_axil_wvalid[s]  = ws_busy[s] && !w_wdone[ws_own[s]];
            m_axil_bready[s]  = ws_busy[s];
            m_axil_araddr[s*ADDR_W +: ADDR_W] = r_addr[rs_own[s]];
            m_axil_arprot[s*3 +: 3]           = r_prot[rs_own[s]];
            m_axil_arvalid[s] = rs_busy[s] && !r_ardone[rs_own[s]];
            m_axil_rready[s]  = rs_busy[s];
        end
    end

    // ---------------------------------------------------------------- state updates
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int m = 0; m < N_M; m++) begin
                w_st[m] <= ST_IDLE; r_st[m] <= ST_IDLE;
                w_awdone[m] <= 1'b0; w_wdone[m] <= 1'b0; r_ardone[m] <= 1'b0;
                w_resp[m] <= 2'b00; r_resp[m] <= 2'b00; r_data[m] <= '0;
                w_addr[m] <= '0; w_prot[m] <= '0; w_data[m] <= '0; w_strb[m] <= '0;
                r_addr[m] <= '0; r_prot[m] <= '0;
            end
            for (int s = 0; s < N_S; s++) begin
                ws_busy[s] <= 1'b0; rs_busy[s] <= 1'b0;
                ws_own[s] <= '0; rs_own[s] <= '0;
                ws_rr[s] <= MW'(N_M - 1); rs_rr[s] <= MW'(N_M - 1);   // the first grant goes to master 0
            end
        end else begin
            // accept: capture the request, then forward it (or answer DECERR)
            for (int m = 0; m < N_M; m++) begin
                if (w_gnt[m]) begin
                    w_addr[m] <= s_axil_awaddr[m*ADDR_W +: ADDR_W];
                    w_prot[m] <= s_axil_awprot[m*3 +: 3];
                    w_data[m] <= s_axil_wdata[m*32 +: 32];
                    w_strb[m] <= s_axil_wstrb[m*4 +: 4];
                    w_awdone[m] <= 1'b0; w_wdone[m] <= 1'b0;
                    if (w_dec[m] == TW'(N_S)) begin w_st[m] <= ST_RESP; w_resp[m] <= DECERR; end
                    else w_st[m] <= ST_FWD;
                end else if (w_st[m] == ST_RESP && s_axil_bready[m]) begin
                    w_st[m] <= ST_IDLE;
                end
                if (r_gnt[m]) begin
                    r_addr[m] <= s_axil_araddr[m*ADDR_W +: ADDR_W];
                    r_prot[m] <= s_axil_arprot[m*3 +: 3];
                    r_ardone[m] <= 1'b0;
                    if (r_dec[m] == TW'(N_S)) begin r_st[m] <= ST_RESP; r_resp[m] <= DECERR; r_data[m] <= '0; end
                    else r_st[m] <= ST_FWD;
                end else if (r_st[m] == ST_RESP && s_axil_rready[m]) begin
                    r_st[m] <= ST_IDLE;
                end
            end
            for (int s = 0; s < N_S; s++) begin
                if (ws_g[s]) begin ws_busy[s] <= 1'b1; ws_own[s] <= ws_gm[s]; ws_rr[s] <= ws_gm[s]; end
                if (rs_g[s]) begin rs_busy[s] <= 1'b1; rs_own[s] <= rs_gm[s]; rs_rr[s] <= rs_gm[s]; end
                if (ws_busy[s]) begin
                    if (m_axil_awvalid[s] && m_axil_awready[s]) w_awdone[ws_own[s]] <= 1'b1;
                    if (m_axil_wvalid[s] && m_axil_wready[s])   w_wdone[ws_own[s]]  <= 1'b1;
                    if (m_axil_bvalid[s]) begin                 // bready is high while the slave is owned
                        w_resp[ws_own[s]] <= m_axil_bresp[s*2 +: 2];
                        w_st[ws_own[s]]   <= ST_RESP;
                        ws_busy[s]        <= 1'b0;
                    end
                end
                if (rs_busy[s]) begin
                    if (m_axil_arvalid[s] && m_axil_arready[s]) r_ardone[rs_own[s]] <= 1'b1;
                    if (m_axil_rvalid[s]) begin                 // rready is high while the slave is owned
                        r_data[rs_own[s]] <= m_axil_rdata[s*32 +: 32];
                        r_resp[rs_own[s]] <= m_axil_rresp[s*2 +: 2];
                        r_st[rs_own[s]]   <= ST_RESP;
                        rs_busy[s]        <= 1'b0;
                    end
                end
            end
        end
    end
endmodule
