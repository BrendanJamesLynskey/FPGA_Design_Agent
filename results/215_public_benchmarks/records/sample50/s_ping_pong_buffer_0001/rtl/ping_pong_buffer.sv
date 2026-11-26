/* verilator lint_off UNUSEDPARAM */
module ping_pong_buffer #(
    parameter int DEPTH = 256,
    parameter int ADDR_WIDTH = 8,
    parameter int DATA_WIDTH = 8
) (
/* verilator lint_on UNUSEDPARAM */
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  write_enable,
    input  logic                  read_enable,
    input  logic [7:0]            data_in,
    output logic [7:0]            data_out,
    output logic                  buffer_full,
    output logic                  buffer_empty,
    output logic                  buffer_select
);

    logic [7:0] write_ptr, read_ptr;
    logic [7:0] dout0, dout1;
    logic       sel_q, full_q, empty_q;

    // Registers reset synchronously; the outputs are also forced to their
    // reset values combinationally while rst_n is low, so the reset is seen
    // at once (no clock edge needed) without an asynchronous register reset.
    assign buffer_select = sel_q   & rst_n;
    assign buffer_full   = full_q  & rst_n;
    assign buffer_empty  = empty_q | ~rst_n;

    wire do_w = write_enable & ~full_q;
    wire do_r = read_enable & ~empty_q;
    wire w_wrap = do_w & (write_ptr == 8'hFF);
    wire r_wrap = do_r & (read_ptr == 8'hFF);

    wire [7:0] wp_n = do_w ? write_ptr + 8'd1 : write_ptr;
    wire [7:0] rp_n = do_r ? read_ptr + 8'd1 : read_ptr;
    wire full_n = w_wrap ? 1'b1 : (r_wrap ? 1'b0 : full_q);

    // no memory write while reset is held
    dual_port_memory memory0 (
        .clk(clk), .we(do_w & ~sel_q & rst_n), .write_addr(write_ptr),
        .din(data_in), .read_addr(read_ptr), .dout(dout0)
    );
    dual_port_memory memory1 (
        .clk(clk), .we(do_w & sel_q & rst_n), .write_addr(write_ptr),
        .din(data_in), .read_addr(read_ptr), .dout(dout1)
    );

    assign data_out = sel_q ? dout1 : dout0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            write_ptr <= 8'd0;
            read_ptr  <= 8'd0;
            sel_q     <= 1'b0;
            full_q    <= 1'b0;
            empty_q   <= 1'b1;
        end else begin
            write_ptr <= wp_n;
            read_ptr  <= rp_n;
            if (r_wrap) sel_q <= ~sel_q;
            full_q    <= full_n;
            empty_q   <= (rp_n == wp_n) & ~full_n;
        end
    end

endmodule
