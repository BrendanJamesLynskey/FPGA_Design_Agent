// pr_top.sv: KR260 placement demonstration of a managed project (brief 102, stage 2): the supplier's block pcs_unit arrives
// already placed and routed and locked (ext/pcs_unit_p0.dcp, filling u_blk), the owned stimulus and sink around it are placed and
// routed by Vivado around the block. The clock pin is the board's 25 MHz oscillator; design.xdc constrains it at 4.0 ns for a
// timing study of the block (the design is not run on a board at that rate).
module pr_top #(
    parameter logic [31:0] BUILD_STAMP = 32'h0
) (
    input  logic       clk_25,
    output logic [1:0] led
);
    logic [3:0] por;                                  // power-on reset: a four-clock shift register (configured flip-flops start at zero)
    logic       rst, din, dout;

    always_ff @(posedge clk_25) por <= {por[2:0], 1'b1};
    assign rst = !por[3];

    pr_src   u_src  (.clk(clk_25), .rst(rst), .bit_o(din));
    pcs_unit u_blk  (.clk(clk_25), .rst(rst), .din(din), .dout(dout));
    pr_sink  u_sink (.clk(clk_25), .rst(rst), .d_i(dout), .led(led));

    /* verilator lint_off UNUSED */
    logic unused;
    assign unused = &{1'b0, BUILD_STAMP};
    /* verilator lint_on UNUSED */
endmodule
