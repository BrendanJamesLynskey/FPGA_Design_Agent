// jtag_regs_map: the common register map of a design on a board with no UART, in front of the design's own registers.
//   0x000 ID (RO)   0x004 BUILD (RO, the bitstream's USR_ACCESS word)   0x008 SCRATCH (RW, resets to 0)   0x010 and up: the design's
// h_* is the register port of jtag_bus (clk domain, byte addresses, h_rdata valid within 2 clocks of h_re and held while h_addr holds).
// u_* is the design's own register port: the same strobes for addresses of 0x010 and above, with the design's read data coming back on u_rdata.
module jtag_regs_map #(
    parameter int DESIGN_ID = 0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] usr_access,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic        u_we,
    output logic        u_re,
    output logic [11:0] u_addr,
    output logic [31:0] u_wdata,
    input  logic [31:0] u_rdata
);
    logic [31:0] scratch;
    wire         own = (h_addr < 12'h010);
    always_ff @(posedge clk) begin
        if (rst) scratch <= '0;
        else if (h_we && h_addr == 12'h008) scratch <= h_wdata;
    end
    always_comb begin
        unique case (h_addr)
            12'h000: h_rdata = DESIGN_ID;
            12'h004: h_rdata = usr_access;
            12'h008: h_rdata = scratch;
            default: h_rdata = own ? 32'h0 : u_rdata;
        endcase
    end
    assign u_we    = h_we && !own;
    assign u_re    = h_re && !own;
    assign u_addr  = h_addr;
    assign u_wdata = h_wdata;
endmodule
