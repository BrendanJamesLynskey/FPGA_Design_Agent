// 2-FF synchroniser plus debounce; press is a one-cycle pulse when the level
// has been high for DEBOUNCE_CYCLES clocks.
module btn_debounce #(
    parameter int DEBOUNCE_CYCLES = 2000000
) (
    input  logic clk,
    input  logic rst,
    input  logic btn,
    output logic press
);
  (* ASYNC_REG = "TRUE" *) logic s1, s2;
  logic [$clog2(DEBOUNCE_CYCLES+1)-1:0] cnt;

  always_ff @(posedge clk) begin
    s1 <= btn;
    s2 <= s1;
  end

  always_ff @(posedge clk) begin
    if (rst || !s2) cnt <= '0;
    else if (cnt != DEBOUNCE_CYCLES[$bits(cnt)-1:0]) cnt <= cnt + 1'b1;
  end

  assign press = s2 && (cnt == DEBOUNCE_CYCLES[$bits(cnt)-1:0] - 1'b1);
endmodule
