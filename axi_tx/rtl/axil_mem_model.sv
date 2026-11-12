// axil_mem_model: an AXI4-Lite memory slave of 2**AW_WORDS 32-bit words, the simulation stand-in for the board's AMD AXI
// BRAM Controller (brief 59A; Icarus cannot run the AMD core). A different slave style from axil_demo_periph on purpose:
// it raises AWREADY and WREADY together, only once both AWVALID and WVALID are high (legal: IHI 0022H A3.3.1 lets a slave
// wait for both), and answers reads two cycles after the AR handshake. Every address in the window is OKAY.
// BUG = 1 (simulation mutant): WSTRB ignored.
module axil_mem_model #(
    parameter int AW_WORDS = 11,
    parameter int BUG      = 0
) (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic [31:0] s_awaddr,
    input  logic [2:0]  s_awprot,
    input  logic        s_awvalid,
    output logic        s_awready,
    input  logic [31:0] s_wdata,
    input  logic [3:0]  s_wstrb,
    input  logic        s_wvalid,
    output logic        s_wready,
    output logic [1:0]  s_bresp,
    output logic        s_bvalid,
    input  logic        s_bready,
    input  logic [31:0] s_araddr,
    input  logic [2:0]  s_arprot,
    input  logic        s_arvalid,
    output logic        s_arready,
    output logic [31:0] s_rdata,
    output logic [1:0]  s_rresp,
    output logic        s_rvalid,
    input  logic        s_rready
);
    logic [31:0] mem [2**AW_WORDS];
    logic        bv = 1'b0, rv = 1'b0, wbusy = 1'b0;
    logic [1:0]  rwait = '0;
    logic [AW_WORDS-1:0] ra = '0;
    initial for (int i = 0; i < 2**AW_WORDS; i++) mem[i] = '0;
    assign s_awready = s_awvalid && s_wvalid && !bv && !wbusy;
    assign s_wready  = s_awready;
    assign s_bvalid  = bv;
    assign s_bresp   = 2'b00;
    assign s_arready = !rv && rwait == 0;
    assign s_rvalid  = rv;
    assign s_rresp   = 2'b00;
    wire [3:0]  st = (BUG != 0) ? 4'hF : s_wstrb;
    wire [31:0] bm = {{8{st[3]}}, {8{st[2]}}, {8{st[1]}}, {8{st[0]}}};
    wire [AW_WORDS-1:0] wa = s_awaddr[AW_WORDS+1:2];
    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            bv <= 1'b0; rv <= 1'b0; rwait <= '0; wbusy <= 1'b0;
        end else begin
            if (s_awready) begin mem[wa] <= (mem[wa] & ~bm) | (s_wdata & bm); bv <= 1'b1; end
            if (bv && s_bready) bv <= 1'b0;
            if (s_arvalid && s_arready) begin ra <= s_araddr[AW_WORDS+1:2]; rwait <= 2'd2; end
            else if (rwait == 2'd1) begin rv <= 1'b1; s_rdata <= mem[ra]; rwait <= '0; end
            else if (rwait != 0) rwait <= rwait - 1'b1;
            if (rv && s_rready) rv <= 1'b0;
        end
    end
endmodule
