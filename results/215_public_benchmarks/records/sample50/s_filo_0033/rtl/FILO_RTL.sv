module FILO_RTL #(
    parameter DATA_WIDTH = 8,  // Width of the data entries
    parameter FILO_DEPTH = 16  // Depth of the FILO buffer
) (
    input  wire                  clk,       // Clock signal
    input  wire                  reset,     // Active-high reset (registers clear synchronously; outputs forced at once)
    input  wire                  push,      // Push control signal
    input  wire                  pop,       // Pop control signal
    input  wire [DATA_WIDTH-1:0] data_in,   // Data input
    output wire [DATA_WIDTH-1:0] data_out,  // Data output
    output wire                  full,      // Full status signal
    output wire                  empty      // Empty status signal
);

  localparam AW = $clog2(FILO_DEPTH);

  (* ram_style = "distributed" *) reg [DATA_WIDTH-1:0] memory[FILO_DEPTH-1:0];
  reg [AW:0] top;

  reg [DATA_WIDTH-1:0] data_out_r;
  reg full_r;
  reg empty_r;

  // Reset takes effect on the outputs immediately (no clock edge needed);
  // the registers themselves are cleared by a synchronous reset.
  assign data_out = reset ? {DATA_WIDTH{1'b0}} : data_out_r;
  assign full     = reset ? 1'b0 : full_r;
  assign empty    = reset ? 1'b1 : empty_r;

  reg feedthrough_valid;
  reg [DATA_WIDTH-1:0] feedthrough_data;

  wire do_ft   = push && pop && empty;
  wire do_push = push && !full;
  wire do_pop  = pop && !empty;

  wire [AW:0] top_m1 = top - 1'b1;
  // top is at most FILO_DEPTH; a read address outside the array returns 0
  wire [DATA_WIDTH-1:0] rd_data = (top_m1 < FILO_DEPTH) ? memory[top_m1[AW-1:0]] : {DATA_WIDTH{1'b0}};

  // Memory write: no reset needed, but no write while reset is asserted
  always @(posedge clk) begin
    if (!reset && !do_ft && do_push && top < FILO_DEPTH) memory[top[AW-1:0]] <= data_in;
  end

  always @(posedge clk) begin
    if (reset) begin
      top <= 0;
      empty_r <= 1;
      full_r <= 0;
      feedthrough_valid <= 0;
      data_out_r <= 0;
    end else begin
      if (do_ft) begin
        data_out_r <= data_in;
        feedthrough_valid <= 1;
      end else begin
        if (do_push) begin
          top <= top + 1'b1;
        end
        if (do_pop) begin
          if (feedthrough_valid) begin
            data_out_r <= feedthrough_data;
            feedthrough_valid <= 0;
          end else begin
            data_out_r <= rd_data;
          end
          if (!do_push) top <= top_m1;
        end
      end
      empty_r <= (top == 0);
      full_r  <= (top == FILO_DEPTH);
    end
  end

  // feedthrough_data is a datapath register: no reset
  always @(posedge clk) begin
    if (do_ft) feedthrough_data <= data_in;
  end
endmodule
