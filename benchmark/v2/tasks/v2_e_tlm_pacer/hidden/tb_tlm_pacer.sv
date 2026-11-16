// Test wrapper: two lanes share one clock. Lane a runs the design with its own PERIOD_MIN (no override), lane b with 16.
module tb_tlm_lane #(
    parameter int CLKS_PER_BIT   = 8,
    parameter int TIMEOUT_CYCLES = 400,
    parameter int FLOOR          = 0
) (
    input  wire         clk,
    input  wire         rstn,
    input  wire         rx_in,
    output wire [15:0]  leds,
    output wire         tx_out
);
    if (FLOOR == 0) begin : g_own
        v2_e_tlm_pacer_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES))
            core (.CLK100MHZ(clk), .CPU_RESETN(rstn), .LED(leds), .UART_TXD_IN(rx_in), .UART_RXD_OUT(tx_out));
    end else begin : g_floor
        v2_e_tlm_pacer_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .PERIOD_MIN(FLOOR))
            core (.CLK100MHZ(clk), .CPU_RESETN(rstn), .LED(leds), .UART_TXD_IN(rx_in), .UART_RXD_OUT(tx_out));
    end
endmodule

module tb_tlm_pacer #(
    parameter int CLKS_PER_BIT   = 8,
    parameter int TIMEOUT_CYCLES = 400
) ();
    logic CLK100MHZ;
    logic CPU_RESETN_a, CPU_RESETN_b;
    logic UART_TXD_IN_a, UART_TXD_IN_b;
    logic [15:0] LED_a;
    logic [15:0] LED_b;
    logic UART_RXD_OUT_a;
    logic UART_RXD_OUT_b;

    initial begin
        CLK100MHZ = 0;
        {CPU_RESETN_a, CPU_RESETN_b} = 2'b00;
        {UART_TXD_IN_a, UART_TXD_IN_b} = 2'b11;
    end

    tb_tlm_lane #(CLKS_PER_BIT, TIMEOUT_CYCLES, 0)  dut_a (CLK100MHZ, CPU_RESETN_a, UART_TXD_IN_a, LED_a, UART_RXD_OUT_a);
    tb_tlm_lane #(CLKS_PER_BIT, TIMEOUT_CYCLES, 16) dut_b (CLK100MHZ, CPU_RESETN_b, UART_TXD_IN_b, LED_b, UART_RXD_OUT_b);
endmodule
