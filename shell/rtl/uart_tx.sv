// uart_tx.sv: 8N1 UART transmitter. A start pulse while idle latches the
// byte; busy is high from the next cycle until the stop bit has been sent.
// Each bit lasts exactly CLKS_PER_BIT clocks. The output is registered.

module uart_tx #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       start,     // ignored while busy
    input  logic [7:0] data,
    output logic       busy,
    output logic       tx         // serial output, idle high
);
    localparam int CW = $clog2(CLKS_PER_BIT + 1);

    logic [9:0]    shreg;        // {stop, data[7:0], start}, sent LSB first
    logic [CW-1:0] cnt;
    logic [3:0]    bits_left;

    always_ff @(posedge clk) begin
        if (rst) begin
            busy      <= 1'b0;
            tx        <= 1'b1;
            shreg     <= '1;
            cnt       <= '0;
            bits_left <= '0;
        end else if (!busy) begin
            tx <= 1'b1;
            if (start) begin
                busy      <= 1'b1;
                shreg     <= {1'b1, data, 1'b0};
                cnt       <= '0;
                bits_left <= 4'd10;
            end
        end else begin
            tx <= shreg[0];
            if (cnt == CW'(CLKS_PER_BIT - 1)) begin
                cnt       <= '0;
                shreg     <= {1'b1, shreg[9:1]};
                bits_left <= bits_left - 1'b1;
                if (bits_left == 4'd1) busy <= 1'b0;
            end else begin
                cnt <= cnt + 1'b1;
            end
        end
    end
endmodule
