// m32_cmpchain: 4-way maximum of 16-bit values (compare and select chain), registered in and out.
module m32_cmpchain (input logic clk, input logic [15:0] a, b, c, d, output logic [15:0] m);
    logic [15:0] aq, bq, cq, dq, m1, m2;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b; cq <= c; dq <= d;
        m1 = aq > bq ? aq : bq; m2 = cq > dq ? cq : dq;
        m <= m1 > m2 ? m1 : m2;
    end
endmodule
