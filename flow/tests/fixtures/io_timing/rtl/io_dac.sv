// io_dac (brief 20 part B): a system-synchronous DAC output. The DAC is clocked by the board's oscillator (fanned out on
// the board), not by the FPGA: its 8 data bits leave from IOB flip-flops on sys_clk. A counter makes the data.
module io_dac (input logic CLK100MHZ, output logic [7:0] dac_d);
    logic [7:0] cnt = '0;
    (* IOB = "true" *) logic [7:0] dac_q = '0;
    always_ff @(posedge CLK100MHZ) begin
        cnt   <= cnt + 8'd3;
        dac_q <= cnt;
    end
    assign dac_d = dac_q;
endmodule
