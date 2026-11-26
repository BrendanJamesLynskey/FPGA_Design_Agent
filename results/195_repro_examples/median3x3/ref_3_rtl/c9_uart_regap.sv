// Re-frames the shell's 7-byte UART response so its bytes leave back to back (no idle gap between
// bytes). The shell inserts a few idle clocks between bytes; this block buffers the 7 bytes and
// sends them as one continuous 8N1 stream. Single clock domain, synchronous reset.
module c9_uart_regap #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic clk,
    input  logic rst,       // synchronous, active high
    input  logic rx_in,     // shell uart_tx output (same clock domain)
    output logic tx_out     // idle high
);
    localparam int CW   = $clog2(CLKS_PER_BIT + 1);
    localparam int HALF = CLKS_PER_BIT / 2;

    // receive side
    logic          rx_busy;
    logic [CW-1:0] rx_cnt;
    logic [3:0]    rx_bit;
    logic [7:0]    rx_sh;
    logic [55:0]   rbuf;
    logic [2:0]    nbuf;
    logic          full;

    // transmit side
    logic          sending;
    logic [CW-1:0] tx_cnt;
    logic [6:0]    tx_left;
    logic [68:0]   tx_sh;

    logic [69:0] pk;
    always_comb begin
        for (int j = 0; j < 7; j++) pk[10*j +: 10] = {1'b1, rbuf[8*j +: 8], 1'b0};
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            rx_busy <= 1'b0;
            rx_cnt  <= '0;
            rx_bit  <= '0;
            rx_sh   <= '0;
            rbuf    <= '0;
            nbuf    <= '0;
            full    <= 1'b0;
            sending <= 1'b0;
            tx_cnt  <= '0;
            tx_left <= '0;
            tx_sh   <= '0;
            tx_out  <= 1'b1;
        end else begin
            // ---- receive
            if (!rx_busy) begin
                if (!rx_in && !sending && !full) begin
                    rx_busy <= 1'b1;
                    rx_cnt  <= '0;
                    rx_bit  <= '0;
                end
            end else if (rx_cnt == CW'((rx_bit == 4'd0) ? HALF - 1 : CLKS_PER_BIT - 1)) begin
                rx_cnt <= '0;
                if (rx_bit == 4'd0) begin
                    if (rx_in) rx_busy <= 1'b0;       // false start
                    else       rx_bit  <= 4'd1;
                end else if (rx_bit <= 4'd8) begin
                    rx_sh  <= {rx_in, rx_sh[7:1]};
                    rx_bit <= rx_bit + 4'd1;
                end else begin
                    rbuf[8*nbuf +: 8] <= rx_sh;
                    rx_busy <= 1'b0;
                    if (nbuf == 3'd6) begin
                        full <= 1'b1;
                        nbuf <= 3'd0;
                    end else begin
                        nbuf <= nbuf + 3'd1;
                    end
                end
            end else begin
                rx_cnt <= rx_cnt + 1'b1;
            end

            // ---- transmit
            if (!sending) begin
                tx_out <= 1'b1;
                if (full) begin
                    full    <= 1'b0;
                    sending <= 1'b1;
                    tx_out  <= pk[0];
                    tx_sh   <= pk[69:1];
                    tx_cnt  <= '0;
                    tx_left <= 7'd69;
                end
            end else if (tx_cnt == CW'(CLKS_PER_BIT - 1)) begin
                tx_cnt <= '0;
                if (tx_left == 7'd0) begin
                    sending <= 1'b0;
                    tx_out  <= 1'b1;
                end else begin
                    tx_out  <= tx_sh[0];
                    tx_sh   <= {1'b1, tx_sh[68:1]};
                    tx_left <= tx_left - 7'd1;
                end
            end else begin
                tx_cnt <= tx_cnt + 1'b1;
            end
        end
    end
endmodule
