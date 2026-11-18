// rst_sync.sv: reset bridge for the active-low asynchronous CPU_RESETN button (the reset synchroniser of
// architecture.yaml). Asserts asynchronously, releases synchronously after two clock edges; the output is an
// active-high synchronous reset for the rest of the design. The only asynchronous reset in the design.

module rst_sync (
    input  logic clk,
    input  logic rst_n_async,   // CPU_RESETN, low = reset
    output logic rst            // active high, synchronous release
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] q;

    always_ff @(posedge clk or negedge rst_n_async) begin
        if (!rst_n_async) q <= 2'b11;
        else              q <= {q[0], 1'b0};
    end

    assign rst = q[1];
endmodule
