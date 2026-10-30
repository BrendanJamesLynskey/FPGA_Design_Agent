// shell_tb_top.sv: the shell with a 16-register read/write window behind it,
// for the shell's own cocotb tests (shell/tests/test_shell_rtl.py).

module shell_tb_top #(
    parameter int CLKS_PER_BIT   = 868,
    parameter int TIMEOUT_CYCLES = 100_000
) (
    input  logic clk,
    input  logic rst,
    input  logic uart_rx,
    output logic uart_tx
);
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic [31:0] regs [16];

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h5348_4C54), .BUILD_STAMP(32'h0)          // "SHLT"
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 16; i++) regs[i] <= '0;
            win_rdata <= '0;
        end else begin
            if (win_wr && win_addr < 7'd16) regs[win_addr[3:0]] <= win_wdata;
            if (win_rd) win_rdata <= (win_addr < 7'd16) ? regs[win_addr[3:0]] : 32'h0;
        end
    end
endmodule
