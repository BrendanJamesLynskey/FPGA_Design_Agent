// c14_nexys_tiny_cnn_top.sv: board top (Nexys A7-100T, master-XDC port names) around the course reference's tiny CNN system.
module c14_nexys_tiny_cnn_top #(
    parameter int DEBOUNCE_CYCLES = 1_000_000,
    parameter int CLKS_PER_BIT    = 868
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    input  logic [15:0] SW,
    output logic [7:0]  AN,
    output logic        CA, CB, CC, CD, CE, CF, CG, DP,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic [6:0] seg;
    cnn_nexys_top_ref #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES), .CLKS_PER_BIT(CLKS_PER_BIT)) u_ref (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .BTNC(BTNC), .SW(SW[2:0]), .AN(AN), .SEG(seg), .LED(LED),
        .UART_RXD_OUT(UART_RXD_OUT));
    assign {CG, CF, CE, CD, CC, CB, CA} = seg;
    assign DP = 1'b1;
endmodule
