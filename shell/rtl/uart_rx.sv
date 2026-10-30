// uart_rx.sv: 8N1 UART receiver. The line is synchronised here, the start bit
// is confirmed at its middle, and each data bit and the stop bit are sampled
// at their middles, CLKS_PER_BIT clocks apart. A low stop bit is a framing
// error: the byte is dropped, frame_err pulses, and the receiver waits for
// the line to go idle (high) before it looks for the next start bit.

module uart_rx #(
    parameter int CLKS_PER_BIT = 868     // 100 MHz / 115200 baud
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       rx,               // asynchronous serial input, idle high
    output logic       valid,            // one-cycle pulse: data holds a byte
    output logic [7:0] data,
    output logic       frame_err         // one-cycle pulse: stop bit was low
);
    localparam int CW   = $clog2(CLKS_PER_BIT + 1);
    localparam int HALF = CLKS_PER_BIT / 2;

    typedef enum logic [2:0] {IDLE, START, DATA, STOP, WAIT_IDLE} state_t;
    state_t       state;
    logic [CW-1:0] cnt;
    logic [2:0]   bitn;
    logic         rx_s;

    sync2 #(.WIDTH(1), .RESET_VALUE(1'b1)) u_sync (.clk(clk), .rst(rst), .d(rx), .q(rx_s));

    always_ff @(posedge clk) begin
        valid     <= 1'b0;
        frame_err <= 1'b0;
        if (rst) begin
            state <= IDLE;
            cnt   <= '0;
            bitn  <= '0;
            data  <= '0;
        end else begin
            case (state)
                IDLE: begin
                    cnt <= '0;
                    if (!rx_s) state <= START;
                end
                START: begin
                    if (cnt == CW'(HALF - 1)) begin
                        cnt  <= '0;
                        bitn <= '0;
                        state <= rx_s ? IDLE : DATA;   // a glitch, not a start bit
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
                DATA: begin
                    if (cnt == CW'(CLKS_PER_BIT - 1)) begin
                        cnt  <= '0;
                        data <= {rx_s, data[7:1]};     // LSB first
                        if (bitn == 3'd7) state <= STOP;
                        bitn <= bitn + 1'b1;
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
                STOP: begin
                    if (cnt == CW'(CLKS_PER_BIT - 1)) begin
                        cnt <= '0;
                        if (rx_s) begin
                            valid <= 1'b1;
                            state <= IDLE;
                        end else begin
                            frame_err <= 1'b1;
                            state     <= WAIT_IDLE;
                        end
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
                WAIT_IDLE: if (rx_s) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
