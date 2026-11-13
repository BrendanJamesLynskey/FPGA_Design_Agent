// bd_axil_regs.sv: a generic AXI4-Lite register bank (brief 65A block-design support). The generator wraps a block
// that has plain ports in it: each control register drives inputs of the block, each status register reads outputs.
//   word 0 .. N_RW-1            control registers, read/write, reset to RW_RESET; byte strobes honoured
//   word N_RW .. N_RW+N_RO-1    status registers, read only (a write answers SLVERR)
//   any other word              SLVERR, read data 0
// rw_wr[i] pulses for one clock after a write to control register i (an arm or clear strobe for the block).
// One write and one read may be in progress at once; each answers one clock after it is accepted.
module bd_axil_regs #(
    parameter int ADDR_W = 12,
    parameter int N_RW   = 1,                                  // 1..64
    parameter int N_RO   = 1,                                  // 1..64
    parameter logic [N_RW*32-1:0] RW_RESET = '0
) (
    input  logic              clk,
    input  logic              rst,
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [31:0]       s_axil_wdata,
    input  logic [3:0]        s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [31:0]       s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,
    output logic [N_RW*32-1:0] rw_q,
    output logic [N_RW-1:0]    rw_wr,
    input  logic [N_RO*32-1:0] ro_d
);
    initial begin
        if (N_RW < 1 || N_RW > 64) $error("bd_axil_regs: N_RW %0d outside 1..64", N_RW);
        if (N_RO < 1 || N_RO > 64) $error("bd_axil_regs: N_RO %0d outside 1..64", N_RO);
        if (ADDR_W < 2 + $clog2(N_RW + N_RO) || ADDR_W > 32) $error("bd_axil_regs: ADDR_W %0d too small for %0d registers", ADDR_W, N_RW + N_RO);
    end

    localparam int IW = ADDR_W - 2;
    logic [IW-1:0] wi, ri;
    assign wi = s_axil_awaddr[ADDR_W-1:2];
    assign ri = s_axil_araddr[ADDR_W-1:2];
    assign s_axil_awready = !s_axil_bvalid && s_axil_awvalid && s_axil_wvalid;
    assign s_axil_wready  = s_axil_awready;
    assign s_axil_arready = !s_axil_rvalid;

    always_ff @(posedge clk) begin
        if (rst) begin
            rw_q <= RW_RESET; rw_wr <= '0; s_axil_bvalid <= 1'b0; s_axil_bresp <= 2'b00;
            s_axil_rvalid <= 1'b0; s_axil_rresp <= 2'b00; s_axil_rdata <= '0;
        end else begin
            rw_wr <= '0;
            if (s_axil_awready) begin
                s_axil_bvalid <= 1'b1;
                s_axil_bresp  <= 2'b10;
                for (int i = 0; i < N_RW; i++)
                    if (wi == IW'(i)) begin
                        for (int b = 0; b < 4; b++)
                            if (s_axil_wstrb[b]) rw_q[i*32 + b*8 +: 8] <= s_axil_wdata[b*8 +: 8];
                        rw_wr[i]     <= 1'b1;
                        s_axil_bresp <= 2'b00;
                    end
            end else if (s_axil_bready) s_axil_bvalid <= 1'b0;
            if (s_axil_arvalid && s_axil_arready) begin
                s_axil_rvalid <= 1'b1;
                s_axil_rresp  <= 2'b10;
                s_axil_rdata  <= '0;
                for (int i = 0; i < N_RW + N_RO; i++)
                    if (ri == IW'(i)) begin
                        s_axil_rresp <= 2'b00;
                        s_axil_rdata <= (i < N_RW) ? rw_q[i*32 +: 32] : ro_d[(i - N_RW)*32 +: 32];
                    end
            end else if (s_axil_rready) s_axil_rvalid <= 1'b0;
        end
    end

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused;          // protection and the byte offset within a word are not used
    assign unused = ^{s_axil_awprot, s_axil_arprot, s_axil_awaddr[1:0], s_axil_araddr[1:0]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
