// Parameterized combinational barrel shifter: shift / rotate, left / right.
module barrel_shifter #(
    parameter int data_width       = 16,
    parameter int shift_bits_width = 4
) (
    input  logic [data_width-1:0]       data_in,
    input  logic [shift_bits_width-1:0] shift_bits,
    input  logic                        left_right,         // 1 = left, 0 = right
    input  logic                        rotate_left_right,  // 1 = rotate, 0 = shift
    output logic [data_width-1:0]       data_out
);

  localparam int W = data_width;

  always_comb begin : shifter
    int unsigned sb;
    int unsigned amt;
    logic [2*W-1:0] dbl;
    logic [2*W-1:0] t;
    sb  = int'(unsigned'(shift_bits));
    amt = sb % unsigned'(W);
    dbl = {data_in, data_in};
    if (rotate_left_right) begin
      t = left_right ? (dbl << amt) : (dbl >> amt);
      data_out = left_right ? t[2*W-1:W] : t[W-1:0];
    end else begin
      // Verilog shifts give zero for amounts >= data_width.
      t = '0;
      data_out = left_right ? (data_in << sb) : (data_in >> sb);
    end
  end

endmodule
