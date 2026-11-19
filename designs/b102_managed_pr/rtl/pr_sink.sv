// pr_sink.sv: the consumer of the placed-and-routed block's serial output: a registered copy and a 24-bit count of ones, whose top
// bit blinks led[0]; led[1] is a slow divider that shows the clock is running. Owned by the project.
module pr_sink (
    input  logic       clk,
    input  logic       rst,
    input  logic       d_i,
    output logic [1:0] led
);
    logic        d_q;
    logic [23:0] ones;
    logic [24:0] div;
    always_ff @(posedge clk) begin
        d_q  <= d_i;
        ones <= rst ? '0 : ones + {23'b0, d_q};
        div  <= rst ? '0 : div + 1'b1;
    end
    assign led = {div[24], ones[23]};
endmodule
