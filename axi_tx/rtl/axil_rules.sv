// axil_rules: the AXI4-Lite protocol rules as a passive monitor of one interface's ports (brief 59A). Port-only, so it can
// watch any master/slave pair, ours or not. viol[i] is high in every clock cycle in which rule i is broken (combinational
// from the ports and one cycle of history); axi_viol_log counts and time-stamps the episodes.
//
// Rules, in our own words, cited to Arm IHI 0022H (AXI) by section; docs/axi_tx.md has the full table:
//   0 AW_HOLD   once AWVALID is high it stays high, with AWADDR and AWPROT unchanged, until AWREADY        (A3.2.1, A3.2.2)
//   1 W_HOLD    the same for WVALID with WDATA and WSTRB                                                      (A3.2.1, A3.2.2)
//   2 B_HOLD    the same for BVALID with BRESP                                                                (A3.2.1, A3.2.2)
//   3 AR_HOLD   the same for ARVALID with ARADDR and ARPROT                                                   (A3.2.1, A3.2.2)
//   4 R_HOLD    the same for RVALID with RDATA and RRESP                                                      (A3.2.1, A3.2.2)
//   5 B_EARLY   BVALID only once both an AW and a W handshake have completed (at an earlier edge) for it      (A3.3.1)
//   6 R_EARLY   RVALID only once an AR handshake has completed for it                                         (A3.3.1)
//   7 RESET     every VALID is low at the first edge at which reset is seen released                          (A3.1.2)
//   8 EXOKAY    no EXOKAY response on AXI4-Lite (it has no exclusive access)                                   (B1.1)
// All rules are ignored while ARESETn is low (signals are don't-care in reset, A3.1.2). Outstanding counts saturate at
// 2**CW - 1 (an AXI4-Lite master with more outstanding transactions than that is outside this checker's scope).
module axil_rules #(
    parameter int ADDR_W = 32,
    parameter int DATA_W = 32,
    parameter int CW     = 8
) (
    input  logic                  aclk,
    input  logic                  aresetn,
    input  logic [ADDR_W-1:0]     awaddr,
    input  logic [2:0]            awprot,
    input  logic                  awvalid,
    input  logic                  awready,
    input  logic [DATA_W-1:0]     wdata,
    input  logic [DATA_W/8-1:0]   wstrb,
    input  logic                  wvalid,
    input  logic                  wready,
    input  logic [1:0]            bresp,
    input  logic                  bvalid,
    input  logic                  bready,
    input  logic [ADDR_W-1:0]     araddr,
    input  logic [2:0]            arprot,
    input  logic                  arvalid,
    input  logic                  arready,
    input  logic [DATA_W-1:0]     rdata,
    input  logic [1:0]            rresp,
    input  logic                  rvalid,
    input  logic                  rready,
    output logic [8:0]            viol
);
    // one cycle of history (initial values: the cycle before time 0 counts as reset)
    logic                p_rstn = 1'b0;
    logic                p_awv = 1'b0, p_awr = 1'b0, p_wv = 1'b0, p_wr = 1'b0, p_bv = 1'b0, p_br = 1'b0;
    logic                p_arv = 1'b0, p_arr = 1'b0, p_rv = 1'b0, p_rr = 1'b0;
    logic [ADDR_W-1:0]   p_awaddr = '0, p_araddr = '0;
    logic [2:0]          p_awprot = '0, p_arprot = '0;
    logic [DATA_W-1:0]   p_wdata = '0, p_rdata = '0;
    logic [DATA_W/8-1:0] p_wstrb = '0;
    logic [1:0]          p_bresp = '0, p_rresp = '0;
    // handshakes completed at earlier edges and not yet answered
    logic [CW-1:0]       aw_pend = '0, w_pend = '0, ar_pend = '0;

    wire awhs = awvalid && awready, whs = wvalid && wready, bhs = bvalid && bready;
    wire arhs = arvalid && arready, rhs = rvalid && rready;
    localparam logic [CW-1:0] MAXC = {CW{1'b1}};

    function automatic logic [CW-1:0] upd(input logic [CW-1:0] c, input logic inc, input logic dec);
        if (inc && !dec)      upd = (c == MAXC) ? c : c + 1'b1;
        else if (dec && !inc) upd = (c == '0) ? c : c - 1'b1;
        else                  upd = c;
    endfunction

    always_ff @(posedge aclk) begin
        p_rstn <= aresetn;
        p_awv <= awvalid; p_awr <= awready; p_awaddr <= awaddr; p_awprot <= awprot;
        p_wv  <= wvalid;  p_wr  <= wready;  p_wdata  <= wdata;  p_wstrb  <= wstrb;
        p_bv  <= bvalid;  p_br  <= bready;  p_bresp  <= bresp;
        p_arv <= arvalid; p_arr <= arready; p_araddr <= araddr; p_arprot <= arprot;
        p_rv  <= rvalid;  p_rr  <= rready;  p_rdata  <= rdata;  p_rresp  <= rresp;
        if (!aresetn) begin
            aw_pend <= '0; w_pend <= '0; ar_pend <= '0;
        end else begin
            aw_pend <= upd(aw_pend, awhs, bhs);
            w_pend  <= upd(w_pend,  whs,  bhs);
            ar_pend <= upd(ar_pend, arhs, rhs);
        end
    end

    wire live = aresetn && p_rstn;            // this cycle and the previous one both out of reset
    always_comb begin
        viol    = '0;
        viol[0] = live && p_awv && !p_awr && (!awvalid || awaddr != p_awaddr || awprot != p_awprot);
        viol[1] = live && p_wv  && !p_wr  && (!wvalid  || wdata  != p_wdata  || wstrb  != p_wstrb);
        viol[2] = live && p_bv  && !p_br  && (!bvalid  || bresp  != p_bresp);
        viol[3] = live && p_arv && !p_arr && (!arvalid || araddr != p_araddr || arprot != p_arprot);
        viol[4] = live && p_rv  && !p_rr  && (!rvalid  || rdata  != p_rdata  || rresp  != p_rresp);
        viol[5] = aresetn && bvalid && (aw_pend == '0 || w_pend == '0);
        viol[6] = aresetn && rvalid && (ar_pend == '0);
        viol[7] = aresetn && !p_rstn && (awvalid || wvalid || bvalid || arvalid || rvalid);
        viol[8] = aresetn && ((bvalid && bresp == 2'b01) || (rvalid && rresp == 2'b01));
    end
endmodule
