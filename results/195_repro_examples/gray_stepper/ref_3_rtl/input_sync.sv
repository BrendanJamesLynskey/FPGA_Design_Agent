// Two-flop synchroniser for the asynchronous BTNU and SW[15] inputs.
module input_sync (
    input  logic       clk,
    input  logic [1:0] d,   // asynchronous
    output logic [1:0] q    // two clocks late
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] s1;
    (* ASYNC_REG = "TRUE" *) logic [1:0] s2;
    always_ff @(posedge clk) begin
        s1 <= d;
        s2 <= s1;
    end
    assign q = s2;
endmodule
