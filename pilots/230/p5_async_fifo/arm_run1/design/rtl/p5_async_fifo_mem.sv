// 512 x 32 asynchronous FIFO storage: block RAM written in clk_wr, read in clk_rd, with the gray
// pointers crossing through XPM CDC primitives.
/* verilator lint_off DECLFILENAME */
module async_fifo (
    input  logic        clk_wr,
    input  logic        clk_rd,
    input  logic        we,
    input  logic [8:0]  waddr,
    input  logic [31:0] wdata,
    input  logic [9:0]  wgray,
    input  logic [8:0]  raddr,
    input  logic [9:0]  rgray,
    output logic [31:0] dout,
    output logic [9:0]  wgray_rd,
    output logic [9:0]  rgray_s
);
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(10)) u_wgray (
        .src_clk(clk_wr), .src_in(wgray), .dest_clk(clk_rd), .dest_out(wgray_rd));
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(10)) u_rgray (
        .src_clk(clk_rd), .src_in(rgray), .dest_clk(clk_wr), .dest_out(rgray_s));

    (* ram_style = "block" *) logic [31:0] mem [0:511];
    always_ff @(posedge clk_wr) if (we) mem[waddr] <= wdata;
    always_ff @(posedge clk_rd) dout <= mem[raddr];
endmodule
