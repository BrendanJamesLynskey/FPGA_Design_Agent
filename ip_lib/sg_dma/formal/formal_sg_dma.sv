// formal_sg_dma.sv: SymbiYosys harness of rtl/sg_dma.sv (brief 241). Everything outside the engine is free: the AXI4-Lite master, the memory
// (arready, awready, wready, rvalid, rdata, rresp, bvalid, bresp are free inputs constrained only to be legal AXI4: a valid is held with its
// payload until its ready, read data only for a burst that was addressed, a write response only after a burst's last beat), the stream
// source and the stream sink. The descriptor words the engine reads are therefore arbitrary: the proofs hold for every buffer address,
// length and ring base software could write.
//
// Asserted on the master's ports, in the AXI rule style of axi_tx/rtl/axil_rules.sv (hold rules, A3.2.1 and A3.2.2; bursts, A3.4.1):
//   H_*   once VALID is high it stays high, with its payload unchanged, until READY: AR, AW, W, the stream port, and the AXI4-Lite B and R
//   B_4K  no burst crosses a 4 KB boundary: (addr mod 4096) + beats * bytes <= 4096, on AR and on AW (the 4 KB proof)
//   B_LEN a burst has at most max(MAX_BURST, descriptor beats) beats; B_SZ AxSIZE is the beat width, or 4 bytes for the one-beat status write;
//   B_INC INCR bursts only; B_AL the address is aligned to the size
//   W_AW  write data only for a burst whose address was accepted earlier; W_LAST wlast on exactly the last beat of the burst
//   O_*   outstanding bursts (accepted, last data or response not yet seen) never exceed OUTSTANDING
// Defines: DIRV=<0|1> (the DIR parameter, so one file serves both), SEEDK (none here: faults are applied to the RTL copy).
module formal_sg_dma #(
    parameter int DATA_W      = 32,
    parameter int MAX_BURST   = 4,
    parameter int OUTSTANDING = 2,
    parameter int DIR         = 0
) (
    input  logic        clk,
    // AXI4-Lite master side (free)
    input  logic        s_axi_awvalid, s_axi_wvalid, s_axi_arvalid, s_axi_bready, s_axi_rready,
    input  logic [5:0]  s_axi_awaddr, s_axi_araddr,
    input  logic [31:0] s_axi_wdata,
    // memory side (free, constrained below)
    input  logic        m_axi_awready, m_axi_wready, m_axi_arready, m_axi_bvalid, m_axi_rvalid,
    input  logic [1:0]  m_axi_bresp, m_axi_rresp,
    input  logic [DATA_W-1:0] m_axi_rdata,
    // stream sides (free, constrained below)
    input  logic        s_axis_tvalid, m_axis_tready,
    input  logic [DATA_W-1:0] s_axis_tdata
);
    localparam int ADDR_W = 32;
    localparam int BYTES = DATA_W / 8;
    localparam int BSH = $clog2(BYTES);
    localparam int DBEATS = 16 / BYTES;
    localparam int MAXLEN = (MAX_BURST > DBEATS) ? MAX_BURST : DBEATS;

    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    wire aresetn = f_past;                           // one clock of reset, then released for good
    logic p_aresetn = 1'b0;
    always_ff @(posedge clk) p_aresetn <= aresetn;
    wire live = aresetn && p_aresetn;                // the reset has been applied at an edge: registers have their reset values

    wire        awvalid, awready_d, wvalid, arvalid, bready, rready, s_axi_awready, s_axi_wready, s_axi_bvalid, s_axi_arready, s_axi_rvalid;
    logic [ADDR_W-1:0] awaddr, araddr;
    logic [7:0] awlen, arlen;
    logic [2:0] awsize, arsize;
    logic [1:0] awburst, arburst, s_axi_bresp, s_axi_rresp;
    logic [3:0] awcache, arcache;
    logic [DATA_W-1:0] wdata, m_axis_tdata;
    logic [DATA_W/8-1:0] wstrb;
    logic wlast, m_axis_tvalid, m_axis_tlast, s_axis_tready, irq;
    logic [31:0] s_axi_rdata;

    sg_dma #(.ADDR_W(ADDR_W), .DATA_W(DATA_W), .MAX_BURST(MAX_BURST), .OUTSTANDING(OUTSTANDING), .DIR(DIR)) dut (
        .aclk(clk), .aresetn(aresetn),
        .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready), .s_axi_awaddr(s_axi_awaddr),
        .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready), .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(4'hF),
        .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready), .s_axi_bresp(s_axi_bresp),
        .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready), .s_axi_araddr(s_axi_araddr),
        .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready), .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
        .m_axi_awvalid(awvalid), .m_axi_awready(m_axi_awready), .m_axi_awaddr(awaddr), .m_axi_awlen(awlen), .m_axi_awsize(awsize),
        .m_axi_awburst(awburst), .m_axi_awcache(awcache),
        .m_axi_wvalid(wvalid), .m_axi_wready(m_axi_wready), .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wlast(wlast),
        .m_axi_bvalid(m_axi_bvalid), .m_axi_bready(bready), .m_axi_bresp(m_axi_bresp),
        .m_axi_arvalid(arvalid), .m_axi_arready(m_axi_arready), .m_axi_araddr(araddr), .m_axi_arlen(arlen), .m_axi_arsize(arsize),
        .m_axi_arburst(arburst), .m_axi_arcache(arcache),
        .m_axi_rvalid(m_axi_rvalid), .m_axi_rready(rready), .m_axi_rdata(m_axi_rdata), .m_axi_rresp(m_axi_rresp), .m_axi_rlast(1'b0),
        .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready), .s_axis_tdata(s_axis_tdata),
        .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tdata(m_axis_tdata), .m_axis_tlast(m_axis_tlast), .irq(irq));

    // ---- history for the hold rules
    logic p_awv = 0, p_awr = 0, p_wv = 0, p_wr = 0, p_arv = 0, p_arr = 0, p_tv = 0, p_tr = 0, p_bv = 0, p_br = 0, p_rv = 0, p_rr = 0;
    logic p_sav = 0, p_sar = 0, p_swv = 0, p_swr = 0, p_sbv = 0, p_sbr = 0, p_srv = 0, p_srr = 0, p_stv = 0, p_str = 0;
    logic [ADDR_W-1:0] p_awaddr, p_araddr;
    logic [7:0] p_awlen, p_arlen;
    logic [2:0] p_awsize, p_arsize;
    logic [DATA_W-1:0] p_wdata, p_mtdata, p_rdata, p_stdata;
    logic [DATA_W/8-1:0] p_wstrb;
    logic p_wlast, p_mtlast;
    logic [1:0] p_sbresp, p_srresp, p_bresp, p_rresp;
    logic [31:0] p_srdata;
    always_ff @(posedge clk) begin
        p_awv <= awvalid; p_awr <= m_axi_awready; p_awaddr <= awaddr; p_awlen <= awlen; p_awsize <= awsize;
        p_wv <= wvalid; p_wr <= m_axi_wready; p_wdata <= wdata; p_wstrb <= wstrb; p_wlast <= wlast;
        p_arv <= arvalid; p_arr <= m_axi_arready; p_araddr <= araddr; p_arlen <= arlen; p_arsize <= arsize;
        p_tv <= m_axis_tvalid; p_tr <= m_axis_tready; p_mtdata <= m_axis_tdata; p_mtlast <= m_axis_tlast;
        p_stv <= s_axis_tvalid; p_str <= s_axis_tready; p_stdata <= s_axis_tdata;
        p_bv <= m_axi_bvalid; p_br <= bready; p_bresp <= m_axi_bresp;
        p_rv <= m_axi_rvalid; p_rr <= rready; p_rdata <= m_axi_rdata; p_rresp <= m_axi_rresp;
        p_sbv <= s_axi_bvalid; p_sbr <= s_axi_bready; p_sbresp <= s_axi_bresp;
        p_srv <= s_axi_rvalid; p_srr <= s_axi_rready; p_srdata <= s_axi_rdata; p_srresp <= s_axi_rresp;
        p_sav <= s_axi_awvalid; p_sar <= s_axi_awready; p_swv <= s_axi_wvalid; p_swr <= s_axi_wready;
    end

    // ---- ghost bookkeeping of the bursts in flight (queues of burst lengths, in beats)
    localparam int QD = 4;
    logic [8:0] rq [QD];           // read bursts accepted (beats), oldest first
    logic [8:0] wq [QD];           // write bursts accepted
    logic [2:0] rn = 0, wn = 0;    // entries; the write queue holds bursts whose data is not all sent
    logic [8:0] r_idx = 0, w_idx = 0;       // beats already taken of the oldest read / write burst
    logic [2:0] wb_n = 0;                   // write bursts fully sent, response still to come
    logic [2:0] ar_open = 0, aw_open = 0;   // read bursts not yet finished, write bursts not yet answered
    wire ar_hs = arvalid && m_axi_arready, aw_hs = awvalid && m_axi_awready, w_hs = wvalid && m_axi_wready;
    wire r_hs = m_axi_rvalid && rready, b_hs = m_axi_bvalid && bready;
    wire [8:0] ar_beats = {1'b0, arlen} + 9'd1, aw_beats = {1'b0, awlen} + 9'd1;
    wire r_end = r_hs && rn != 0 && (r_idx == rq[0] - 9'd1);
    wire w_end = w_hs && wn != 0 && (w_idx == wq[0] - 9'd1);
    always_ff @(posedge clk) begin
        if (!aresetn) begin rn <= 0; wn <= 0; r_idx <= 0; w_idx <= 0; wb_n <= 0; ar_open <= 0; aw_open <= 0; end
        else begin
            if (ar_hs) begin rq[rn - (r_end ? 3'd1 : 3'd0)] <= ar_beats; end
            if (r_end) begin for (int i = 0; i < QD - 1; i++) rq[i] <= rq[i + 1]; end
            if (ar_hs && r_end) begin rq[rn - 3'd1] <= ar_beats; end
            rn <= rn + (ar_hs ? 3'd1 : 3'd0) - (r_end ? 3'd1 : 3'd0);
            r_idx <= r_end ? 9'd0 : (r_hs && rn != 0 ? r_idx + 9'd1 : r_idx);
            ar_open <= ar_open + (ar_hs ? 3'd1 : 3'd0) - (r_end ? 3'd1 : 3'd0);

            if (aw_hs) begin wq[wn - (w_end ? 3'd1 : 3'd0)] <= aw_beats; end
            if (w_end) begin for (int i = 0; i < QD - 1; i++) wq[i] <= wq[i + 1]; end
            if (aw_hs && w_end) begin wq[wn - 3'd1] <= aw_beats; end
            wn <= wn + (aw_hs ? 3'd1 : 3'd0) - (w_end ? 3'd1 : 3'd0);
            w_idx <= w_end ? 9'd0 : (w_hs && wn != 0 ? w_idx + 9'd1 : w_idx);
            wb_n <= wb_n + (w_end ? 3'd1 : 3'd0) - (b_hs && wb_n != 0 ? 3'd1 : 3'd0);
            aw_open <= aw_open + (aw_hs ? 3'd1 : 3'd0) - (b_hs ? 3'd1 : 3'd0);
        end
    end

    // ---- the environment is legal AXI4 (assumptions)
    always_comb if (live) begin
        // valids are held with their payload until accepted
        if (p_rv && !p_rr) assume (m_axi_rvalid && m_axi_rdata == p_rdata && m_axi_rresp == p_rresp);
        if (p_bv && !p_br) assume (m_axi_bvalid && m_axi_bresp == p_bresp);
        if (p_stv && !p_str) assume (s_axis_tvalid && s_axis_tdata == p_stdata);
        if (p_sbv && !p_sbr) assume (1'b1);
        // read data only inside an accepted read burst; a response only after a burst's last data beat
        if (m_axi_rvalid) assume (rn != 0 || (ar_hs && 1'b0));
        if (m_axi_bvalid) assume (wb_n != 0);
        // the AXI4-Lite master holds its valids until accepted
        if (p_sav && !p_sar) assume (s_axi_awvalid);
        if (p_swv && !p_swr) assume (s_axi_wvalid);
    end
    always_ff @(posedge clk) if (live) begin
        if (p_sav && !p_sar) assume (s_axi_awaddr == $past(s_axi_awaddr));
        if (p_swv && !p_swr) assume (s_axi_wdata == $past(s_axi_wdata));
    end
    logic [5:0] pa_ar; logic p_sarv = 0, p_sarr = 0;
    always_ff @(posedge clk) begin
        pa_ar <= s_axi_araddr; p_sarv <= s_axi_arvalid; p_sarr <= s_axi_arready;
        if (live && p_sarv && !p_sarr) assume (s_axi_arvalid && s_axi_araddr == pa_ar);
    end
    // the one clock of reset: nothing is offered
    always_comb if (!aresetn) assume (!m_axi_rvalid && !m_axi_bvalid && !s_axis_tvalid && !s_axi_awvalid && !s_axi_wvalid && !s_axi_arvalid);

    // ---- the properties
    wire [12:0] ar_end = {1'b0, araddr[11:0]} + (({5'b0, arlen} + 13'd1) << arsize);
    wire [12:0] aw_end = {1'b0, awaddr[11:0]} + (({5'b0, awlen} + 13'd1) << awsize);
    always_ff @(posedge clk) if (live) begin
        // hold rules (all five channels of the master, the stream port, the AXI4-Lite response channels)
        if (p_arv && !p_arr) assert (arvalid && araddr == p_araddr && arlen == p_arlen && arsize == p_arsize);        // H_AR
        if (p_awv && !p_awr) assert (awvalid && awaddr == p_awaddr && awlen == p_awlen && awsize == p_awsize);        // H_AW
        if (p_wv && !p_wr) assert (wvalid && wdata == p_wdata && wstrb == p_wstrb && wlast == p_wlast);               // H_W
        if (p_tv && !p_tr) assert (m_axis_tvalid && m_axis_tdata == p_mtdata && m_axis_tlast == p_mtlast);            // H_AXIS
        if (p_sbv && !p_sbr) assert (s_axi_bvalid && s_axi_bresp == p_sbresp);                                        // H_LITE_B
        if (p_srv && !p_srr) assert (s_axi_rvalid && s_axi_rdata == p_srdata && s_axi_rresp == p_srresp);             // H_LITE_R
    end
    always_comb if (live) begin
        if (arvalid) begin
            assert (ar_end <= 13'd4096);                                    // B_4K (read)
            assert ({1'b0, arlen} + 9'd1 <= MAXLEN);                         // B_LEN
            assert (arsize == BSH && arburst == 2'b01);                      // B_SZ, B_INC
            assert ((araddr & ((1 << arsize) - 1)) == 0);                    // B_AL
        end
        if (awvalid) begin
            assert (aw_end <= 13'd4096);                                    // B_4K (write)
            assert ({1'b0, awlen} + 9'd1 <= MAXLEN);
            assert ((awsize == BSH) || (awsize == 3'd2 && awlen == 8'd0));
            assert (awburst == 2'b01);
            assert ((awaddr & ((1 << awsize) - 1)) == 0);
        end
    end
`ifdef GHOST
    // properties that need the bookkeeping above: bounded (bmc) proofs, because the bookkeeping is not tied to the engine's own counters
    always_comb if (live) begin
        if (wvalid) begin
            assert (wn != 0);                                                // W_AW
            assert (wlast == (w_idx == wq[0] - 9'd1));                      // W_LAST
        end
        assert (ar_open <= OUTSTANDING);                                     // O_R
        assert (aw_open <= OUTSTANDING);                                     // O_W
    end
`endif
`ifdef COVER
    // each cover is a state the properties above would be empty without: bursts of more than one beat, the last beat of a stream packet or of a
    // burst, the outstanding limit reached, and a status write that completes (the engine got through a whole descriptor)
    always_ff @(posedge clk) if (live) begin
        if (DIR == 0) begin
            cover (arvalid && arlen != 0);
            cover (m_axis_tvalid && m_axis_tlast);
            cover (ar_open == OUTSTANDING);
        end else begin
            cover (awvalid && awlen != 0);
            cover (wvalid && wlast && wn != 0);
            cover (aw_open == OUTSTANDING);
        end
        cover (b_hs);
    end
`endif
endmodule
