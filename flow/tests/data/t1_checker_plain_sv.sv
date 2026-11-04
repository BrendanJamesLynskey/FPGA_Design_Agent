// Port-only cover checker for t1_top. Covers only; no assertions.
module t1_checker (
    input logic        clk,
    input logic        cpu_resetn,
    input logic        btnu,
    input logic        btnd,
    input logic        btnc,
    input logic [15:0] sw,
    input logic [15:0] led,
    input logic [6:0]  seg,
    input logic [7:0]  an,
    input logic        dp,
    input logic        uart_rxd,
    input logic        uart_txd
);
  logic seen_rst = 1'b0;
  always @(posedge clk) if (!cpu_resetn) seen_rst <= 1'b1;
  wire ok = seen_rst && cpu_resetn;

  C_btnu_press:     cover property (@(posedge clk) ok && btnu);
  C_btnd_press:     cover property (@(posedge clk) ok && btnd);
  C_btnc_press:     cover property (@(posedge clk) ok && btnc);
  C_led_on:         cover property (@(posedge clk) ok && (|led));
  C_display_blank:  cover property (@(posedge clk) ok && (an == 8'hFF));
  C_digit_on:       cover property (@(posedge clk) ok && (an[3:0] != 4'hF));
  C_left_digit_on:  cover property (@(posedge clk) ok && (an[7:6] != 2'b11));
  C_uart_tx_active: cover property (@(posedge clk) ok && !uart_txd);
  C_uart_rx_active: cover property (@(posedge clk) ok && !uart_rxd);
  C_sw_nonzero:     cover property (@(posedge clk) ok && (|sw[7:0]));
endmodule

bind t1_top t1_checker u_t1_checker (.*);
