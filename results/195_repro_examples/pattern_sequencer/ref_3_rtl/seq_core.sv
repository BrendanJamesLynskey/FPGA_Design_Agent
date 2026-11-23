// Sequencer core: tick generator, duration countdown, index, loops, pause, LED.
module seq_core #(
    parameter int TICK_CYCLES = 100000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        stop,
    input  logic        oneshot,
    input  logic [4:0]  length,
    input  logic [15:0][15:0] pat,
    input  logic [15:0][7:0]  dur,
    input  logic        press,
    output logic        running,
    output logic        paused,
    output logic        finished,
    output logic [3:0]  index,
    output logic [15:0] loops,
    output logic [15:0] led
);
  localparam int TW = (TICK_CYCLES > 1) ? $clog2(TICK_CYCLES) : 1;
  logic [TW-1:0] tick_cnt;
  logic [8:0]    rem;

  wire tick = (tick_cnt == TW'(TICK_CYCLES - 1));
  wire last = ({1'b0, index} >= (length - 5'd1));
  wire [3:0] nxt = last ? 4'd0 : index + 4'd1;
  wire [7:0] nd = dur[nxt];
  wire [7:0] d0 = dur[0];

  always_ff @(posedge clk) begin
    if (rst) begin
      running  <= 1'b0;
      paused   <= 1'b0;
      finished <= 1'b0;
      index    <= 4'd0;
      loops    <= 16'd0;
      tick_cnt <= '0;
      rem      <= 9'd0;
    end else begin
      if (press && running) paused <= !paused;
      if (running && !paused) begin
        tick_cnt <= tick ? '0 : tick_cnt + 1'b1;
        if (tick) begin
          if (rem == 9'd1) begin
            if (last && loops != 16'hFFFF) loops <= loops + 16'd1;
            if (last && oneshot) begin
              running  <= 1'b0;
              finished <= 1'b1;
              paused   <= 1'b0;
            end else begin
              index <= nxt;
              rem   <= (nd == 8'd0) ? 9'd256 : {1'b0, nd};
            end
          end else begin
            rem <= rem - 9'd1;
          end
        end
      end
      if (stop) begin
        running <= 1'b0;
        paused  <= 1'b0;
      end
      if (start) begin
        running  <= 1'b1;
        paused   <= 1'b0;
        finished <= 1'b0;
        index    <= 4'd0;
        loops    <= 16'd0;
        tick_cnt <= '0;
        rem      <= (d0 == 8'd0) ? 9'd256 : {1'b0, d0};
      end
    end
  end

  always_ff @(posedge clk) begin
    if (rst) led <= 16'h0;
    else led <= (running || finished) ? pat[index] : 16'h0;
  end
endmodule
