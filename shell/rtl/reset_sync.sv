// reset_sync.sv: reset bridge for an active-low asynchronous reset button.
// Asserts asynchronously, releases synchronously (two clock edges after the
// button is let go), so every flop leaves reset on the same edge. The output
// is an active-high synchronous reset for the rest of the design.

module reset_sync (
    input  logic clk,
    input  logic rst_n_async,   // e.g. CPU_RESETN, low = reset
    output logic rst            // active high, synchronous release
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] q;

    always_ff @(posedge clk or negedge rst_n_async) begin
        if (!rst_n_async) q <= 2'b11;
        else              q <= {q[0], 1'b0};
    end

    assign rst = q[1];
endmodule
