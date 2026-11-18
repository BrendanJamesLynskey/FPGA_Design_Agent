// rst_sync: asynchronous assert, synchronous release; active-high output reset.
module rst_sync (
    input  logic clk,
    input  logic arst_n,   // asynchronous, active low (button)
    output logic rst       // active high, synchronous to clk
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] q;

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) q <= 2'b11;
        else         q <= {q[0], 1'b0};
    end

    assign rst = q[1];
endmodule
