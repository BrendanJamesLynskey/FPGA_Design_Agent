// bd_win_axil_master.sv: the test shell's register window as an AXI4-Lite master (block-design support).
// The host reaches every slave of a block design through five window registers; one AXI4-Lite transfer at a time:
//   0x00 ADDR   RW  byte address of the next transfer
//   0x01 WDATA  RW  write data
//   0x02 CTRL   W   bit0 start a write (ADDR, WDATA, strobes [7:4]; 0 means all four bytes), bit1 start a read;
//                   ignored while busy; reads 0
//   0x03 STATUS R   bit0 busy, bit1 done (the last transfer finished), [3:2] its response (0 OKAY, 2 SLVERR, 3 DECERR),
//                   [31:16] transfers finished since reset (wraps)
//   0x04 RDATA  R   data of the last read
// Window reads are registered (valid the clock after win_rd), as the shell requires. The AXI4-Lite side raises VALID
// without waiting for READY, holds it with its payload until the handshake, and keeps BREADY and RREADY high.
module bd_win_axil_master #(
    parameter int ADDR_W = 32
) (
    input  logic              clk,
    input  logic              rst,
    input  logic [6:0]        win_addr,
    input  logic              win_wr,
    input  logic              win_rd,
    input  logic [31:0]       win_wdata,
    output logic [31:0]       win_rdata,
    output logic [ADDR_W-1:0] m_axil_awaddr,
    output logic [2:0]        m_axil_awprot,
    output logic              m_axil_awvalid,
    input  logic              m_axil_awready,
    output logic [31:0]       m_axil_wdata,
    output logic [3:0]        m_axil_wstrb,
    output logic              m_axil_wvalid,
    input  logic              m_axil_wready,
    input  logic [1:0]        m_axil_bresp,
    input  logic              m_axil_bvalid,
    output logic              m_axil_bready,
    output logic [ADDR_W-1:0] m_axil_araddr,
    output logic [2:0]        m_axil_arprot,
    output logic              m_axil_arvalid,
    input  logic              m_axil_arready,
    input  logic [31:0]       m_axil_rdata,
    input  logic [1:0]        m_axil_rresp,
    input  logic              m_axil_rvalid,
    output logic              m_axil_rready
);
    // Parameter guard: an initial block, so it stops a simulation; synthesis ignores it (the generator checks first).
    initial if (ADDR_W < 12 || ADDR_W > 32) $error("bd_win_axil_master: ADDR_W %0d outside 12..32", ADDR_W);

    logic [31:0] addr, wdata, rdata;
    logic [3:0]  strb;
    logic        busy, done, is_rd, aw_done, w_done, ar_done;
    logic [1:0]  resp;
    logic [15:0] count;

    assign m_axil_awaddr  = addr[ADDR_W-1:0];
    assign m_axil_araddr  = addr[ADDR_W-1:0];
    assign m_axil_awprot  = 3'b000;
    assign m_axil_arprot  = 3'b000;
    assign m_axil_wdata   = wdata;
    assign m_axil_wstrb   = strb;
    assign m_axil_awvalid = busy && !is_rd && !aw_done;
    assign m_axil_wvalid  = busy && !is_rd && !w_done;
    assign m_axil_bready  = busy && !is_rd;
    assign m_axil_arvalid = busy && is_rd && !ar_done;
    assign m_axil_rready  = busy && is_rd;

    always_ff @(posedge clk) begin
        if (rst) begin
            addr <= '0; wdata <= '0; rdata <= '0; strb <= 4'hF; busy <= 1'b0; done <= 1'b0; is_rd <= 1'b0;
            aw_done <= 1'b0; w_done <= 1'b0; ar_done <= 1'b0; resp <= 2'b00; count <= '0;
        end else begin
            if (win_wr) case (win_addr)
                7'h00: if (!busy) addr  <= win_wdata;
                7'h01: if (!busy) wdata <= win_wdata;
                7'h02: if (!busy && (win_wdata[0] || win_wdata[1])) begin
                    busy <= 1'b1; done <= 1'b0; is_rd <= win_wdata[1] && !win_wdata[0];
                    strb <= (win_wdata[7:4] == 4'h0) ? 4'hF : win_wdata[7:4];
                    aw_done <= 1'b0; w_done <= 1'b0; ar_done <= 1'b0;
                end
                default: ;
            endcase
            if (m_axil_awvalid && m_axil_awready) aw_done <= 1'b1;
            if (m_axil_wvalid && m_axil_wready)   w_done  <= 1'b1;
            if (m_axil_arvalid && m_axil_arready) ar_done <= 1'b1;
            if (m_axil_bready && m_axil_bvalid) begin
                busy <= 1'b0; done <= 1'b1; resp <= m_axil_bresp; count <= count + 1'b1;
            end
            if (m_axil_rready && m_axil_rvalid) begin
                busy <= 1'b0; done <= 1'b1; resp <= m_axil_rresp; rdata <= m_axil_rdata; count <= count + 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) case (win_addr)
            7'h00: win_rdata <= addr;
            7'h01: win_rdata <= wdata;
            7'h03: win_rdata <= {count, 12'h0, resp, done, busy};
            7'h04: win_rdata <= rdata;
            default: win_rdata <= '0;
        endcase
    end
endmodule
