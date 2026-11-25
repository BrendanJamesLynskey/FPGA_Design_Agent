// jtag_regs: the host's register window over the board's JTAG cable for a board with no PL UART (KR260): jtag_bus (BSCANE2 USER4) plus the
// common register map (jtag_regs_map: ID, BUILD = USR_ACCESS, SCRATCH) and the design's own register port u_* for addresses 0x010 and up.
// Simulate jtag_regs_map and the design's registers by driving h_*/u_* directly: jtag_bus holds Xilinx primitives (BSCANE2, xpm_cdc).
module jtag_regs #(
    parameter int DESIGN_ID = 0
) (
    input  logic        clk,                 // a free-running clock; the registers live in this domain
    input  logic        rst,                 // hold for a few clocks at start
    output logic        u_we,
    output logic        u_re,
    output logic [11:0] u_addr,
    output logic [31:0] u_wdata,
    input  logic [31:0] u_rdata
);
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata, usr_access;
`ifdef SYNTHESIS
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(usr_access), .DATAVALID());
`else
    assign usr_access = 32'h0;
`endif
    jtag_bus u_bus (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata));
    jtag_regs_map #(.DESIGN_ID(DESIGN_ID)) u_map (.clk(clk), .rst(rst), .usr_access(usr_access), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .u_we(u_we), .u_re(u_re), .u_addr(u_addr), .u_wdata(u_wdata), .u_rdata(u_rdata));
endmodule
