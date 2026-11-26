module t1_pattern_sequencer_top #(
    parameter int CLKS_PER_BIT = 868,
    parameter int TIMEOUT_CYCLES = 1000000,
    parameter logic [31:0] BUILD_STAMP = 32'h0,
    parameter int DEBOUNCE_CYCLES = 2000000,
    parameter int TICK_CYCLES = 100000,
    /* verilator lint_off UNUSEDPARAM */
    parameter int NUM_STEPS = 16  // fixed at 16 by the step memory
    /* verilator lint_on UNUSEDPARAM */
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
  logic rst;
  reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

  logic [6:0]  win_addr;
  logic        win_wr, win_rd;
  logic [31:0] win_wdata, win_rdata;

  fpga_shell #(
      .CLKS_PER_BIT(CLKS_PER_BIT),
      .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
      .DESIGN_ID(32'h50534551),
      .BUILD_STAMP(BUILD_STAMP)
  ) u_shell (
      .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
      .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
      .win_wdata(win_wdata), .win_rdata(win_rdata));

  logic press, start, stop, oneshot, running, paused, finished;
  logic [4:0] length;
  logic [3:0] index;
  logic [15:0] loops;
  logic [15:0][15:0] pat;
  logic [15:0][7:0]  dur;

  btn_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_db (
      .clk(CLK100MHZ), .rst(rst), .btn(BTNC), .press(press));

  seq_regs u_regs (
      .clk(CLK100MHZ), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
      .win_wdata(win_wdata), .win_rdata(win_rdata),
      .start(start), .stop(stop), .oneshot(oneshot), .length(length), .pat(pat), .dur(dur),
      .running(running), .paused(paused), .finished(finished), .index(index), .loops(loops));

  seq_core #(.TICK_CYCLES(TICK_CYCLES)) u_core (
      .clk(CLK100MHZ), .rst(rst), .start(start), .stop(stop), .oneshot(oneshot),
      .length(length), .pat(pat), .dur(dur), .press(press),
      .running(running), .paused(paused), .finished(finished), .index(index),
      .loops(loops), .led(LED));
endmodule
