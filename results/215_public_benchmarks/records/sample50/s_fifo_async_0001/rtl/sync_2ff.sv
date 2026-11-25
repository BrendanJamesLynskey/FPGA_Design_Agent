// Two-flip-flop synchroniser for a Gray-coded pointer (single clock domain: the destination).
// Synchronous active-high reset, as the spec asks for the pointer resets.
module sync_2ff #(
    parameter int WIDTH = 5
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] d,
    output logic [WIDTH-1:0] q,
    output logic [WIDTH-1:0] q1   // first stage (next value of q)
);
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] s1;
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] s2;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1 <= '0;
            s2 <= '0;
        end else begin
            s1 <= d;
            s2 <= s1;
        end
    end

    assign q  = s2;
    assign q1 = s1;
endmodule
