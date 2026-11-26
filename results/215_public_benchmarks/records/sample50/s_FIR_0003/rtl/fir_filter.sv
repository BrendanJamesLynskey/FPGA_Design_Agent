// 8-tap windowed FIR filter with selectable coefficient set (unsigned).
// Reset is active high and synchronous (design standard STD-RST-01).
module fir_filter #(
    /* verilator lint_off UNUSEDPARAM */
    parameter int NUM_TAPS   = 8,  // documentation only: the tap count is fixed at 8
    /* verilator lint_on UNUSEDPARAM */
    parameter int DATA_WIDTH = 16,
    parameter int NORM_SHIFT = 4
) (
    input  logic                  clk,
    input  logic                  reset,
    input  logic [DATA_WIDTH-1:0] data_in,
    input  logic [1:0]            window_type,
    output logic [DATA_WIDTH-1:0] data_out
);

  logic [DATA_WIDTH-1:0] shift_reg0, shift_reg1, shift_reg2, shift_reg3;
  logic [DATA_WIDTH-1:0] shift_reg4, shift_reg5, shift_reg6, shift_reg7;

  logic [4:0]  coeff [0:7];
  logic [31:0] sum;

  always_comb begin
    case (window_type)
      2'b00:   begin coeff[0]=5'd10; coeff[1]=5'd11; coeff[2]=5'd12; coeff[3]=5'd13;
                     coeff[4]=5'd14; coeff[5]=5'd15; coeff[6]=5'd16; coeff[7]=5'd17; end
      2'b01:   begin coeff[0]=5'd2;  coeff[1]=5'd4;  coeff[2]=5'd8;  coeff[3]=5'd12;
                     coeff[4]=5'd12; coeff[5]=5'd8;  coeff[6]=5'd4;  coeff[7]=5'd2;  end
      2'b10:   begin coeff[0]=5'd3;  coeff[1]=5'd6;  coeff[2]=5'd9;  coeff[3]=5'd11;
                     coeff[4]=5'd11; coeff[5]=5'd9;  coeff[6]=5'd6;  coeff[7]=5'd3;  end
      default: begin coeff[0]=5'd1;  coeff[1]=5'd2;  coeff[2]=5'd5;  coeff[3]=5'd9;
                     coeff[4]=5'd9;  coeff[5]=5'd5;  coeff[6]=5'd2;  coeff[7]=5'd1;  end
    endcase
  end

  assign sum = 32'(shift_reg0) * 32'(coeff[0]) + 32'(shift_reg1) * 32'(coeff[1])
             + 32'(shift_reg2) * 32'(coeff[2]) + 32'(shift_reg3) * 32'(coeff[3])
             + 32'(shift_reg4) * 32'(coeff[4]) + 32'(shift_reg5) * 32'(coeff[5])
             + 32'(shift_reg6) * 32'(coeff[6]) + 32'(shift_reg7) * 32'(coeff[7]);

  always_ff @(posedge clk) begin
    if (reset) begin
      shift_reg0 <= '0; shift_reg1 <= '0; shift_reg2 <= '0; shift_reg3 <= '0;
      shift_reg4 <= '0; shift_reg5 <= '0; shift_reg6 <= '0; shift_reg7 <= '0;
      data_out   <= '0;
    end else begin
      shift_reg0 <= data_in;
      shift_reg1 <= shift_reg0;
      shift_reg2 <= shift_reg1;
      shift_reg3 <= shift_reg2;
      shift_reg4 <= shift_reg3;
      shift_reg5 <= shift_reg4;
      shift_reg6 <= shift_reg5;
      shift_reg7 <= shift_reg6;
      data_out   <= DATA_WIDTH'(sum >> NORM_SHIFT);
    end
  end

endmodule
