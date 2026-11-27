// rst_gen: internal power-up reset for the clk_c3 domain, active high, held for HOLD clocks after configuration.
// Reset model "reprogram": the registers take their value from the bitstream, so initial values are used (no reset input).
module rst_gen #(
    parameter int HOLD = 8
) (
    input  logic clk,
    output logic rst
);
    logic [7:0] cnt  = 8'd0;
    logic       rst_q = 1'b1;
    always_ff @(posedge clk) begin
        if (cnt == 8'(HOLD)) begin
            rst_q <= 1'b0;
        end else begin
            cnt <= cnt + 8'd1;
        end
    end
    assign rst = rst_q;
endmodule
