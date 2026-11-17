// Reset synchroniser: asynchronous assert (button, active low), synchronous release.
// Output rst is active high, used everywhere inside the design.
// The flops are asynchronously set, so they power up set (reset asserted).
module v2_e_udp_endpoint_rst_sync (
    input  logic clk,
    input  logic arst_n,
    output logic rst
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] sync_q;

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) sync_q <= 2'b11;
        else         sync_q <= {sync_q[0], 1'b0};
    end

    assign rst = sync_q[1];
endmodule
