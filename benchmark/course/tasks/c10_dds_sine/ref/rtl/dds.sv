// Part 10 lesson 5 exercise: a direct digital synthesiser: a phase accumulator, a sine look-up table and a registered output.
//
// Every clock: acc <= acc + fw (AW bits, wraps), and out_data <= LUT[top LA bits of the OLD acc]. So out_data on clock k (k = 0 for the first clock
// after reset is released) is LUT[(k * fw mod 2^AW) >> (AW - LA)] and the low AW - LA bits of the phase are thrown away (phase truncation, which
// makes spurs). The table has 2^LA entries of a full cycle: LUT[i] = floor((2^(OW-1) - 1) * sin(2 pi i / 2^LA) + 0.5), signed OW bits. out_valid is
// low in reset and high from the first clock after it. The output frequency is fw / 2^AW times the clock rate. rst_n is synchronous, active low.
module dds #(
    parameter int AW = 24,
    parameter int LA = 8,
    parameter int OW = 12
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic [AW-1:0]        fw,
    output logic                 out_valid,
    output logic signed [OW-1:0] out_data
);
    logic signed [OW-1:0] lut [2**LA];
    logic [AW-1:0] acc;

    initial begin
        for (int i = 0; i < 2**LA; i++)
            lut[i] = OW'($rtoi($floor((2.0**(OW-1) - 1.0) * $sin(6.283185307179586 * i / (2.0**LA)) + 0.5)));
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            acc <= '0; out_valid <= 1'b0; out_data <= '0;
        end else begin
            acc <= acc + fw;
            out_data <= lut[acc[AW-1 -: LA]];
            out_valid <= 1'b1;
        end
    end
endmodule
