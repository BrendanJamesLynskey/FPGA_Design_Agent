// divider_hr_cpa_step: one radix-4 SRT step with a carry-propagate partial remainder (brief 139c), combinational.
//   u is the W + 1 bit two's-complement remainder; the step forms 4u - q*b with one adder. The digit comes from the top bits of u (exact
//   estimate) and the divisor's top bits through the same selection table as the carry-save version. first = 1: the dividend a is in u[W-1:0], used unshifted.
module divider_hr_cpa_step #(
    parameter int W = 16
) (
    input  logic         first,
    input  logic [W:0]   u,
    input  logic [W-1:0] b,
    output logic [W:0]   u_n,
    output logic [2:0]   q
);
    localparam int WW = W + 3;
    logic [WW-1:0] x, z, m1, m2, s;
    logic [6:0]    est;
    logic          cin;

    assign x   = first ? {3'b000, u[W-1:0]} : {u, 2'b00};
    assign est = first ? {3'b000, u[W-1:W-4]} : u[W:W-6];

    divider_hr_digit u_digit (.i(b[W-2:W-4]), .k($signed(est)), .q(q));

    assign m1 = {3'b000, b};
    assign m2 = {2'b00, b, 1'b0};
    always_comb begin
        case (q)
            3'b001:  begin z = ~m1; cin = 1'b1; end
            3'b010:  begin z = ~m2; cin = 1'b1; end
            3'b111:  begin z = m1;  cin = 1'b0; end
            3'b110:  begin z = m2;  cin = 1'b0; end
            default: begin z = '0;  cin = 1'b0; end
        endcase
    end
    assign s   = x + z + (WW)'(cin);
    assign u_n = s[W:0];
    logic unused;
    assign unused = &{1'b0, s[WW-1:W+1]};
endmodule
