module cvdp_copilot_mem_allocator #(
  parameter int SIZE  = 4,
  parameter int ADDRW = $clog2(SIZE)
) (
  input  logic             clk,
  input  logic             reset,
  input  logic             acquire_en,
  output logic [ADDRW-1:0] acquire_addr,
  input  logic             release_en,
  input  logic [ADDRW-1:0] release_addr,
  output logic             empty,
  output logic             full
);
  logic [SIZE-1:0]  free_slots, free_slots_n;
  logic [ADDRW-1:0] free_index;
  logic             lz_all_zero;
  logic             full_d;

  always_comb begin
    free_slots_n = free_slots;
    if (acquire_en) free_slots_n[acquire_addr] = 1'b0;
    if (release_en) free_slots_n[release_addr] = 1'b1;
  end

  cvdp_leading_zero_cnt #(.DATA_WIDTH(SIZE), .OUT_WIDTH(ADDRW), .REVERSE(1'b1)) u_lzc (
    .data(free_slots_n), .leading_zeros(free_index), .all_zeros(lz_all_zero)
  );

  assign full_d = lz_all_zero;

  always_ff @(posedge clk) begin
    if (reset) begin
      free_slots   <= '1;
      acquire_addr <= '0;
      empty        <= 1'b1;
      full         <= 1'b0;
    end else begin
      free_slots   <= free_slots_n;
      acquire_addr <= free_index;
      full         <= full_d;
      empty        <= (free_slots_n == '1);
    end
  end
endmodule

/* verilator lint_off DECLFILENAME */
// Leading/trailing zero counter. REVERSE=1 counts trailing zeros (index of lowest set bit).
// All-zero input gives count 0.
module cvdp_leading_zero_cnt #(
  parameter int DATA_WIDTH = 4,
  parameter int OUT_WIDTH  = (DATA_WIDTH > 1) ? $clog2(DATA_WIDTH) : 1,
  parameter bit REVERSE    = 1'b0
) (
  input  logic [DATA_WIDTH-1:0] data,
  output logic [OUT_WIDTH-1:0]  leading_zeros,
  output logic                  all_zeros
);
  always_comb begin
    leading_zeros = '0;
    all_zeros     = (data == '0);
    if (REVERSE) begin
      for (int i = DATA_WIDTH - 1; i >= 0; i--)
        if (data[i]) leading_zeros = OUT_WIDTH'(i);
    end else begin
      for (int i = 0; i < DATA_WIDTH; i++)
        if (data[i]) leading_zeros = OUT_WIDTH'(DATA_WIDTH - 1 - i);
    end
    if (all_zeros) leading_zeros = '0;
  end
endmodule
