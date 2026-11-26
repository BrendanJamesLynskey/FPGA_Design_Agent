// Both modules live in this one file as the spec requires.
/* verilator lint_off DECLFILENAME */
// Parameterised priority encoder: index of the highest set bit, 0 if none.
module priority_encoder #(
    parameter N = 8,
    parameter M = 3
) (
    input  wire [N-1:0] input_signal,
    output reg  [M-1:0] out
);
    integer i;
    always @(*) begin
        out = {M{1'b0}};
        for (i = 0; i < N; i = i + 1) begin
            if (input_signal[i]) out = i[M-1:0];
        end
    end
endmodule

// Cascaded encoder: two half-width encoders plus a select.
module cascaded_encoder #(
    parameter N = 8,
    parameter M = 3
) (
    input  wire [N-1:0] input_signal,
    output wire [M-1:0] out,
    output wire [M-2:0] out_upper_half,
    output wire [M-2:0] out_lower_half
);
    wire upper_nz = |input_signal[N-1:N/2];
    wire lower_nz = |input_signal[N/2-1:0];

    priority_encoder #(.N(N/2), .M(M-1)) u_upper (
        .input_signal(input_signal[N-1:N/2]),
        .out(out_upper_half)
    );
    priority_encoder #(.N(N/2), .M(M-1)) u_lower (
        .input_signal(input_signal[N/2-1:0]),
        .out(out_lower_half)
    );

    assign out = upper_nz ? {1'b1, out_upper_half} :
                 lower_nz ? {1'b0, out_lower_half} : {M{1'b0}};
endmodule
/* verilator lint_on DECLFILENAME */
