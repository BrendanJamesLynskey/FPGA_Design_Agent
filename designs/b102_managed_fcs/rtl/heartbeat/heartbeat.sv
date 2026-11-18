// heartbeat.sv: a free-running divider whose top bit blinks an LED; the project's EXCLUDED component (kept out of the agent's
// view, built and signed off with the design).
module heartbeat #(parameter int W = 26) (
    input  logic clk,
    input  logic rst,
    output logic blink
);
    logic [W-1:0] c;
    always_ff @(posedge clk) c <= rst ? '0 : c + 1'b1;
    assign blink = c[W-1];
endmodule
