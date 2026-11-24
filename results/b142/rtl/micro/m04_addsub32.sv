// m04_addsub32: 32-bit add or subtract under a control input, carry in.
module m04_addsub32 (input logic clk, input logic [31:0] a, b, input logic sub, cin, output logic [32:0] s);
    logic [31:0] aq, bq; logic subq, cinq;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b; subq <= sub; cinq <= cin;
        s <= subq ? ({1'b0, aq} - {1'b0, bq} - cinq) : ({1'b0, aq} + {1'b0, bq} + cinq);
    end
endmodule
