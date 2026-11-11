// io_adc (brief 20 part B): a system-synchronous ADC input. The board's 100 MHz oscillator clocks both the ADC and the
// FPGA (CLK100MHZ), so the ADC's data is timed against sys_clk. The 8 data bits are captured in IOB flip-flops; a button
// (BTNC, asynchronous, two-flop synchroniser), an LED and the UART transmit pin are the slow ports of fixture I9/I10.
module io_adc (input logic CLK100MHZ, input logic [7:0] adc_d, input logic BTNC,
               output logic [0:0] LED, output logic UART_RXD_OUT);
    (* IOB = "true" *) logic [7:0] adc_q = '0;
    logic [7:0] sum = '0;
    (* ASYNC_REG = "true" *) logic [1:0] btn_sync = '0;
    logic led_q = 1'b0, tx_q = 1'b1;
    always_ff @(posedge CLK100MHZ) begin
        adc_q    <= adc_d;
        sum      <= sum + adc_q;
        btn_sync <= {btn_sync[0], BTNC};
        led_q    <= btn_sync[1] ^ sum[7];
        tx_q     <= ~(^sum);
    end
    assign LED[0] = led_q;
    assign UART_RXD_OUT = tx_q;
endmodule
