// m35_mac_ce_rst: multiply-accumulate with a clock enable and a synchronous reset on the accumulator (DSP48E2 CEP and RSTP).
module m35_mac_ce_rst (input logic clk, input logic en, rst, input logic signed [17:0] a, b, output logic signed [47:0] acc);
    logic signed [17:0] aq, bq; logic signed [35:0] m; logic enq, rstq;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b; m <= aq * bq; enq <= en; rstq <= rst;
        if (rstq) acc <= '0; else if (enq) acc <= acc + m;
    end
endmodule
