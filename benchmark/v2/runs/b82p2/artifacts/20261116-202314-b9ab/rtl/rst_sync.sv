// rst_sync: two-flop synchroniser for the asynchronous active-low CPU_RESETN button.
// Output is an active-high reset, synchronous to clk; the only inversion of the reset.
module rst_sync (
    input  logic clk,
    input  logic rst_n_async,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic q0;
    (* ASYNC_REG = "TRUE" *) logic q1;

    always_ff @(posedge clk) begin
        q0 <= ~rst_n_async;
        q1 <= q0;
    end

    assign rst = q1;
endmodule
