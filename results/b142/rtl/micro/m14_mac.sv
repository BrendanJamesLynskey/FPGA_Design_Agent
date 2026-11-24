// m14_mac: multiply-accumulate, acc <= acc + a*b, with an accumulator clear (P-register feedback).
module m14_mac (input logic clk, input logic clr, input logic signed [17:0] a, b, output logic signed [47:0] acc);
    logic signed [17:0] aq, bq; logic signed [35:0] m; logic clrq, clrq2;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b; m <= aq * bq; clrq <= clr; clrq2 <= clrq;
        acc <= (clrq2 ? 48'sd0 : acc) + m;
    end
endmodule
