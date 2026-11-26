// XOR accumulator: o_unique_number ^= i_number on each i_clk edge with i_ready high.
// Reset: i_rst_n is an asynchronous active-low clear required by the spec (REQ-03).
module unique_number_identifier #(
    parameter int p_bit_width   = 8,
    /* verilator lint_off UNUSEDPARAM */
    parameter int p_max_numbers = 16
    /* verilator lint_on UNUSEDPARAM */
) (
    input  logic                    i_clk,
    input  logic                    i_rst_n,
    input  logic                    i_ready,
    input  logic [p_bit_width-1:0]  i_number,
    output logic [p_bit_width-1:0]  o_unique_number
);

  always_ff @(posedge i_clk or negedge i_rst_n) begin
    if (!i_rst_n)      o_unique_number <= '0;
    else if (i_ready)  o_unique_number <= o_unique_number ^ i_number;
  end

endmodule
