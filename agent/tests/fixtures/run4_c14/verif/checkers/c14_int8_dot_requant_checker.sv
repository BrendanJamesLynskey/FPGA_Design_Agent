// Port-only checker for c14_int8_dot_requant_top (bound; compiles to nothing in Icarus).
`include "v_macros.svh"

module c14_int8_dot_requant_checker (
    input wire clk,
    input wire rst,
    input wire led,
    input wire rxd_out,
    input wire txd_in
);
    reg seen_rst = 1'b0;
    reg past_ok = 1'b0;
    // seen_rst also rises after the first clock, so a run whose reset pulse is
    // missed by the sampler still evaluates the covers (the properties are boolean-only).
    always @(posedge clk) begin
        past_ok <= 1'b1;
        if (rst || !past_ok) seen_rst <= 1'b1;
    end

    `V_SAME(A_led_boolean, 1'b1, (led == 1'b0) || (led == 1'b1))
    `V_NEXT(A_tx_boolean, 1'b1, (rxd_out == 1'b0) || (rxd_out == 1'b1))

    `V_COVER(C_led_high, led)
    `V_COVER(C_led_fall, !led && $past(led))
    `V_COVER(C_led_rise, led && !$past(led))
    `V_COVER(C_tx_start, !rxd_out && $past(rxd_out))
    `V_COVER(C_rx_start, !txd_in && $past(txd_in))
endmodule

`ifndef __ICARUS__
bind c14_int8_dot_requant_top c14_int8_dot_requant_checker u_chk (
    .clk(CLK100MHZ), .rst(!CPU_RESETN), .led(LED0), .rxd_out(UART_RXD_OUT), .txd_in(UART_TXD_IN)
);
`endif
