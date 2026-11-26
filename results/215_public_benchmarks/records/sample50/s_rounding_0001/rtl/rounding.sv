// Combinational IEEE rounding module
module rounding #(
    parameter int WIDTH = 24
) (
    input  logic [WIDTH-1:0] in_data,
    input  logic             sign,
    input  logic             roundin,
    input  logic             stickyin,
    input  logic [2:0]       rm,
    output logic [WIDTH-1:0] out_data,
    output logic             inexact,
    output logic             cout,
    output logic             r_up
);

  always_comb begin
    case (rm)
      3'b000:  r_up = roundin & (stickyin | in_data[0]);
      3'b010:  r_up = (roundin | stickyin) & ~sign;
      3'b011:  r_up = (roundin | stickyin) & sign;
      3'b100:  r_up = roundin;
      default: r_up = 1'b0;
    endcase
  end

  logic [WIDTH:0] sum;
  assign sum      = {1'b0, in_data} + {{WIDTH{1'b0}}, r_up};
  assign out_data = sum[WIDTH-1:0];
  assign cout     = sum[WIDTH];
  assign inexact  = roundin | stickyin;

endmodule
