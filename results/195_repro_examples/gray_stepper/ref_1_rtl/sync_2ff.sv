// Two-flop synchroniser for an asynchronous single-bit input.
module sync_2ff (
    input  logic clk,
    input  logic d,
    output logic q
);
    (* ASYNC_REG = "TRUE" *) logic s1;
    (* ASYNC_REG = "TRUE" *) logic s2;

    always_ff @(posedge clk) begin
        s1 <= d;
        s2 <= s1;
    end

    assign q = s2;
endmodule
