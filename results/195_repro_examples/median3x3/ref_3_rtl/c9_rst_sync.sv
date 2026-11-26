// Two-flop synchroniser of the active-low push-button reset to an active-high synchronous reset.
module c9_rst_sync (
    input  logic clk,
    input  logic rstn_async,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic q1;
    (* ASYNC_REG = "TRUE" *) logic q2;
    always_ff @(posedge clk) begin
        q1 <= ~rstn_async;
        q2 <= q1;
    end
    assign rst = q2;
endmodule
