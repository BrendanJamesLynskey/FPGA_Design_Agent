// source: labs/p16_crypto/aes_uart_system.sv (course file, unchanged below this line)
// Part 16 lab 1 and agent project p16_nexys_aes_uart, the working core (checked in Icarus by test_lab_uart.py): AES-128 encryption over a UART. Protocol (8N1): the host sends 32 bytes, the key (16 bytes, byte 0
// first) and then the plaintext block (16 bytes, byte 0 first); about 270 clocks of UART-independent latency later the board answers with the 16 ciphertext bytes (byte 0 first). Nothing is stored between blocks.
// Uses the course's iterative AES-128 (solutions/p16l02_aes128 with its S-box table). THE KEY ARRIVES OVER THE UART: this is a bench demonstration of the datapath, not a way to protect a key.
module aes_uart_system #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic clk,
    input  logic rst_n,
    input  logic rxd,
    output logic txd,
    output logic busy
);
    logic        rx_vld, tx_busy, tx_go;
    logic [7:0]  rx_data, tx_data;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk, .rst_n, .rxd, .vld(rx_vld), .data(rx_data));
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (.clk, .rst_n, .go(tx_go), .data(tx_data), .busy(tx_busy), .txd);
    logic [255:0] sh;
    logic [5:0]   nrx;
    logic         a_start, a_busy, a_done;
    logic [127:0] ct;
    aes128 u_aes (.clk, .rst_n, .start(a_start), .key(sh[255:128]), .pt(sh[127:0]), .busy(a_busy), .done(a_done), .ct);
    typedef enum logic [1:0] {S_RX, S_RUN, S_TX} st_t;
    st_t st;
    logic [4:0] k;
    logic [1:0] ph;
    assign busy = (st != S_RX);
    assign a_start = (st == S_RUN) && (ph == 2'd0);
    assign tx_go = (st == S_TX) && (ph == 2'd0) && !tx_busy;
    assign tx_data = ct[127 - 8*k -: 8];
    always_ff @(posedge clk) begin
        if (!rst_n) begin st <= S_RX; nrx <= '0; ph <= '0; k <= '0; end
        else case (st)
            S_RX: if (rx_vld) begin
                sh <= {sh[247:0], rx_data};
                if (nrx == 6'd31) begin nrx <= '0; st <= S_RUN; ph <= 2'd0; end else nrx <= nrx + 1'b1;
            end
            S_RUN: case (ph)
                2'd0: ph <= 2'd1;                                   // start pulse is high in this clock
                default: if (a_done) begin st <= S_TX; ph <= 2'd0; k <= '0; end
            endcase
            S_TX: case (ph)
                2'd0: if (tx_go) ph <= 2'd1;
                2'd1: if (tx_busy) ph <= 2'd2;
                default: if (!tx_busy) begin
                    ph <= 2'd0;
                    k <= k + 1'b1;
                    if (k == 5'd15) st <= S_RX;
                end
            endcase
            default: st <= S_RX;
        endcase
    end
endmodule
