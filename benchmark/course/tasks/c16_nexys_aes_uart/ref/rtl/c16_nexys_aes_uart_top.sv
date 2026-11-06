// P16 reference top-level for the Nexys A7-100T: AES-128 over the UART. Reset synchroniser and busy LED filled in (the lab skeleton leaves them as blanks).
module c16_nexys_aes_uart_top #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [0:0]  LED
);
    logic r1, r2;
    always_ff @(posedge CLK100MHZ) begin r1 <= CPU_RESETN; r2 <= r1; end
    aes_uart_system #(.CLKS_PER_BIT(CLKS_PER_BIT)) u (.clk(CLK100MHZ), .rst_n(r2), .rxd(UART_TXD_IN), .txd(UART_RXD_OUT), .busy(LED[0]));
endmodule
