// Part 11 lesson 3 solution: an NCO and a complex mixer (digital down-conversion step).
module nco_mixer #(
    parameter int AW = 16,
    parameter int LA = 8,
    parameter int XW = 12
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 en,
    input  logic [AW-1:0]        fw,
    input  logic signed [XW-1:0] x,
    output logic                 out_valid,
    output logic signed [XW-1:0] i_out,
    output logic signed [XW-1:0] q_out
);
    localparam int CW = 16;
    logic signed [CW-1:0] lut [2**LA];
    logic [AW-1:0] acc;

    initial begin
        for (int i = 0; i < 2**LA; i++)
            lut[i] = CW'($rtoi($floor(16383.0 * $sin(6.283185307179586 * i / (2.0**LA)) + 0.5)));
    end

    wire [LA-1:0] idx = acc[AW-1 -: LA];
    wire signed [CW-1:0] s = lut[idx];
    wire signed [CW-1:0] c = lut[idx + LA'(2**(LA-2))];
    wire signed [XW+CW-1:0] pi = x * c;
    wire signed [XW+CW-1:0] pq = x * (-s);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            acc <= '0; out_valid <= 1'b0; i_out <= '0; q_out <= '0;
        end else begin
            out_valid <= en;
            if (en) begin
                acc   <= acc + fw;
                i_out <= XW'(pi >>> 14);
                q_out <= XW'(pq >>> 14);
            end
        end
    end
endmodule
