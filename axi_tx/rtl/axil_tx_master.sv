// axil_tx_master: the transactor's AXI4-Lite master engine (brief 59A). One transaction at a time: the sequencer
// (axi_tx_seq) hands it a read or a write with its timing knobs; done pulses with the response, read data and latency.
//
// Timing knobs, all drawn from the throttle LFSR `thr` (stepped every cycle by the sequencer, so a run replays exactly):
//   valid_p   before raising each VALID, wait another cycle while thr[7:0] (AW, AR) or thr[23:16] (W) < valid_p
//             (valid_p = 0: VALID as early as possible, back to back)
//   ready_p   BREADY / RREADY high in a cycle when thr[15:8] <= ready_p (255: always; 0: one cycle in 256)
//   order     0: AWVALID and WVALID raised in the same cycle; 1: AW first, WVALID raised at least max(gap,1) cycles
//             after AWVALID; 2: W first, the same the other way. The second VALID never waits for the first READY
//             (a master that waits for AWREADY before WVALID breaks IHI 0022H A3.3.1).
//   inject    deliberate master-side protocol faults, to show the checker on hardware: 1 drop AWVALID (writes) or
//             ARVALID (reads) for one cycle after one stalled cycle; 2 change WDATA bit 0 after one stalled cycle.
// Latency counts clock cycles from the cycle after start to the response handshake.
/* verilator lint_off UNUSEDSIGNAL */   // the throttle LFSR's top byte is the stream's
module axil_tx_master #(
    parameter int ADDR_W = 32,
    parameter int DATA_W = 32
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  start,
    input  logic                  is_read,
    input  logic [ADDR_W-1:0]     addr,
    input  logic [DATA_W-1:0]     wdata,
    input  logic [DATA_W/8-1:0]   wstrb,
    input  logic [1:0]            order,
    input  logic [7:0]            gap,
    input  logic [1:0]            inject,
    input  logic [31:0]           thr,
    input  logic [7:0]            valid_p,
    input  logic [7:0]            ready_p,
    output logic                  busy,
    output logic                  done,
    output logic [1:0]            resp,
    output logic [DATA_W-1:0]     rdata,
    output logic [31:0]           latency,
    output logic                  pend_aw,      // which handshake the transaction is waiting for (watchdog report)
    output logic                  pend_w,
    output logic                  pend_b,
    output logic                  pend_ar,
    output logic                  pend_r,
    // AXI4-Lite master port
    output logic [ADDR_W-1:0]     m_awaddr,
    output logic [2:0]            m_awprot,
    output logic                  m_awvalid,
    input  logic                  m_awready,
    output logic [DATA_W-1:0]     m_wdata,
    output logic [DATA_W/8-1:0]   m_wstrb,
    output logic                  m_wvalid,
    input  logic                  m_wready,
    input  logic [1:0]            m_bresp,
    input  logic                  m_bvalid,
    output logic                  m_bready,
    output logic [ADDR_W-1:0]     m_araddr,
    output logic [2:0]            m_arprot,
    output logic                  m_arvalid,
    input  logic                  m_arready,
    input  logic [DATA_W-1:0]     m_rdata,
    input  logic [1:0]            m_rresp,
    input  logic                  m_rvalid,
    output logic                  m_rready
);
    logic        active = 1'b0, rd = 1'b0;
    logic        aw_up = 1'b0, w_up = 1'b0, aw_ok = 1'b0, w_ok = 1'b0, ar_up = 1'b0, ar_ok = 1'b0;
    logic        awv = 1'b0, wv = 1'b0, arv = 1'b0;
    logic [1:0]  ord = '0, inj = '0;
    logic [7:0]  gap_r = '0, since = '0;
    logic        inj_left = 1'b0, inj_drop = 1'b0, flip = 1'b0;
    logic [ADDR_W-1:0]   addr_r = '0;
    logic [DATA_W-1:0]   wdata_r = '0;
    logic [DATA_W/8-1:0] wstrb_r = '0;
    logic [31:0] lat = '0;

    initial begin done = 1'b0; resp = '0; rdata = '0; latency = '0; end

    wire go_a = (thr[7:0]   >= valid_p);          // draw: AW / AR VALID may rise this cycle
    wire go_w = (thr[23:16] >= valid_p);          // draw: W VALID may rise this cycle
    wire rdy  = (thr[15:8]  <= ready_p);
    wire [7:0] gap1 = (gap_r == 0) ? 8'd1 : gap_r;

    assign m_awaddr  = addr_r;
    assign m_araddr  = addr_r;
    assign m_awprot  = 3'b000;
    assign m_arprot  = 3'b000;
    assign m_wdata   = wdata_r ^ DATA_W'(flip);
    assign m_wstrb   = wstrb_r;
    assign m_awvalid = awv;
    assign m_wvalid  = wv;
    assign m_arvalid = arv;
    assign m_bready  = active && !rd && aw_ok && w_ok && rdy;
    assign m_rready  = active && rd && ar_ok && rdy;
    assign busy      = active;
    assign pend_aw   = active && !rd && !aw_ok;
    assign pend_w    = active && !rd && !w_ok;
    assign pend_b    = active && !rd && aw_ok && w_ok;
    assign pend_ar   = active && rd && !ar_ok;
    assign pend_r    = active && rd && ar_ok;

    wire awhs = awv && m_awready, whs = wv && m_wready, arhs = arv && m_arready;
    wire bhs = m_bready && m_bvalid, rhs = m_rready && m_rvalid;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            active <= 1'b0; awv <= 1'b0; wv <= 1'b0; arv <= 1'b0; aw_up <= 1'b0; w_up <= 1'b0; ar_up <= 1'b0;
            aw_ok <= 1'b0; w_ok <= 1'b0; ar_ok <= 1'b0; flip <= 1'b0; inj_drop <= 1'b0; inj_left <= 1'b0;
        end else if (!active) begin
            if (start) begin
                active <= 1'b1; rd <= is_read; addr_r <= addr; wdata_r <= wdata; wstrb_r <= wstrb; ord <= order;
                gap_r <= gap; inj <= inject; inj_left <= (inject != 2'd0); lat <= '0; since <= '0;
                aw_up <= 1'b0; w_up <= 1'b0; ar_up <= 1'b0; aw_ok <= 1'b0; w_ok <= 1'b0; ar_ok <= 1'b0;
                flip <= 1'b0; inj_drop <= 1'b0;
            end
        end else begin
            lat <= lat + 1'b1;
            if (aw_up || w_up) since <= (since == 8'hFF) ? since : since + 1'b1;
            if (rd) begin
                // ---- read: AR, then R
                if (!ar_up) begin
                    if (go_a) begin arv <= 1'b1; ar_up <= 1'b1; end
                end else if (arhs) begin
                    arv <= 1'b0; ar_ok <= 1'b1;
                end else if (inj_drop) begin
                    arv <= 1'b1; inj_drop <= 1'b0;                       // re-raise after the injected drop
                end else if (arv && inj_left && inj == 2'd1) begin
                    arv <= 1'b0; inj_drop <= 1'b1; inj_left <= 1'b0;     // inject 1: ARVALID dropped while stalled
                end
                if (rhs) begin
                    done <= 1'b1; resp <= m_rresp; rdata <= m_rdata; latency <= lat + 1'b1; active <= 1'b0;
                end
            end else begin
                // ---- write: AW and W in the chosen order, then B
                if (!aw_up && !w_up && ord == 2'd0) begin
                    if (go_a) begin awv <= 1'b1; wv <= 1'b1; aw_up <= 1'b1; w_up <= 1'b1; end
                end else begin
                    if (!aw_up && (ord != 2'd2 || (w_up && since >= gap1)) && go_a) begin awv <= 1'b1; aw_up <= 1'b1; end
                    if (!w_up  && (ord != 2'd1 || (aw_up && since >= gap1)) && go_w) begin wv <= 1'b1; w_up <= 1'b1; end
                end
                if (awhs) begin
                    awv <= 1'b0; aw_ok <= 1'b1;
                end else if (inj_drop && !awv && aw_up && !aw_ok) begin
                    awv <= 1'b1; inj_drop <= 1'b0;
                end else if (awv && inj_left && inj == 2'd1) begin
                    awv <= 1'b0; inj_drop <= 1'b1; inj_left <= 1'b0;     // inject 1: AWVALID dropped while stalled
                end
                if (whs) begin
                    wv <= 1'b0; w_ok <= 1'b1;
                end else if (wv && inj_left && inj == 2'd2) begin
                    flip <= 1'b1; inj_left <= 1'b0;                      // inject 2: WDATA changed while stalled
                end
                if (bhs) begin
                    done <= 1'b1; resp <= m_bresp; rdata <= '0; latency <= lat + 1'b1; active <= 1'b0;
                end
            end
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
