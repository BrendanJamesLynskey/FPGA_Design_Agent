// 2-flop synchroniser for an asynchronous input (BTNU, SW[15]); synchronous reset.
module input_sync (
    input  logic clk,
    input  logic rst,
    input  logic d,
    output logic q
);
    (* ASYNC_REG = "TRUE" *) logic s1;
    (* ASYNC_REG = "TRUE" *) logic s2;
    always_ff @(posedge clk) begin
        if (rst) begin
            s1 <= 1'b0;
            s2 <= 1'b0;
        end else begin
            s1 <= d;
            s2 <= s1;
        end
    end
    assign q = s2;
endmodule
