// sync2.sv: two-flop synchroniser for an asynchronous input bus (buttons,
// switches, UART RX). Each bit is synchronised on its own; use it only for
// signals whose bits are independent or quasi-static.

module sync2 #(
    parameter int          WIDTH = 1,
    parameter logic [WIDTH-1:0] RESET_VALUE = '0
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] d,     // asynchronous
    output logic [WIDTH-1:0] q      // synchronous to clk, two cycles late
);
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] s1;
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] s2;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1 <= RESET_VALUE;
            s2 <= RESET_VALUE;
        end else begin
            s1 <= d;
            s2 <= s1;
        end
    end

    assign q = s2;
endmodule
