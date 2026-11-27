// rst_gen: power-on reset for the register bus. Reset model "reprogram": no reset input,
// registers start from their initial values; rst is high for RESET_HOLD_CYCLES clocks after configuration.
module rst_gen #(
    parameter int RESET_HOLD_CYCLES = 16
) (
    input  logic clk,
    output logic rst
);
    localparam int W = $clog2(RESET_HOLD_CYCLES + 1);
    logic [W-1:0] cnt   = '0;
    logic         rst_q = 1'b1;

    always_ff @(posedge clk) begin
        if (cnt == W'(RESET_HOLD_CYCLES)) rst_q <= 1'b0;
        else                              cnt   <= cnt + 1'b1;
    end

    assign rst = rst_q;
endmodule
