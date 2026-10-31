// spi_burst.sv: SPI master, mode 0 (CPOL 0, CPHA 0), MSB first. One transfer
// = chip select low, NBYTES bytes out of tx (byte 0 first) while the same
// number of bytes come back into rx, chip select high. SCLK is HALF clocks low
// and HALF high (50 = 1 MHz at 100 MHz). MOSI changes while SCLK is low; MISO
// is sampled at the end of each high half.

module spi_burst #(
    parameter int HALF = 50
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic [3:0]  nbytes,     // 1..8 (0 is taken as 1, above 8 as 8)
    input  logic [63:0] tx,         // byte i in [8i+7:8i]
    output logic [63:0] rx,
    output logic        busy,
    output logic        done,
    output logic        sclk,
    output logic        mosi,
    output logic        cs_n,
    input  logic        miso        // synchronised
);
    typedef enum logic [2:0] {S_IDLE, S_SETUP, S_HIGH, S_LOW, S_HOLD, S_GAP} st_t;
    st_t         st;
    logic [15:0] div;
    logic [6:0]  bits_left;          // bits still to clock, including the current one
    logic [63:0] sh;                 // outgoing bits, the current one in [63]
    logic        tick;

    assign tick = (st != S_IDLE) && (div == 16'(HALF - 1));
    assign mosi = sh[63];            // a flop output: changes only while SCLK is low

    function automatic logic [63:0] reorder(input logic [63:0] v);
        // byte 0 is sent first and MSB first, so it goes to the top of the shifter
        for (int i = 0; i < 8; i++) reorder[63 - 8*i -: 8] = v[8*i +: 8];
    endfunction

    function automatic logic [6:0] nbits(input logic [3:0] n);
        if (n == 4'd0)      nbits = 7'd8;
        else if (n >= 4'd8) nbits = 7'd64;
        else                nbits = {1'b0, n[2:0], 3'b000};
    endfunction

    logic [63:0] rx_sh;              // incoming bits, first bit ends at the top after all shifts
    logic [6:0]  total;

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; div <= '0; bits_left <= '0; sh <= '0; rx_sh <= '0; rx <= '0; total <= '0;
            busy <= 1'b0; done <= 1'b0; sclk <= 1'b0; cs_n <= 1'b1;
        end else begin
            div <= tick ? '0 : (st == S_IDLE ? '0 : div + 16'd1);
            unique case (st)
                S_IDLE: if (go) begin
                    st <= S_SETUP; busy <= 1'b1; done <= 1'b0;
                    sh <= reorder(tx); rx_sh <= '0; bits_left <= nbits(nbytes); total <= nbits(nbytes);
                    cs_n <= 1'b0; sclk <= 1'b0;
                end
                S_SETUP: if (tick) begin st <= S_HIGH; sclk <= 1'b1; end
                S_HIGH:  if (tick) begin
                    rx_sh <= {rx_sh[62:0], miso};
                    sclk  <= 1'b0;
                    if (bits_left == 7'd1) st <= S_HOLD;
                    else begin
                        st <= S_LOW; bits_left <= bits_left - 7'd1;
                        sh <= {sh[62:0], 1'b0};
                    end
                end
                S_LOW:   if (tick) begin st <= S_HIGH; sclk <= 1'b1; end
                S_HOLD:  if (tick) begin st <= S_GAP; cs_n <= 1'b1; sh <= '0; end
                S_GAP:   if (tick) begin
                    st <= S_IDLE; busy <= 1'b0; done <= 1'b1;
                    // rx_sh holds `total` bits with the last one at bit 0: move byte 0 to rx[7:0]
                    for (int i = 0; i < 8; i++)
                        rx[8*i +: 8] <= (7'(8*i) < total) ? 8'(rx_sh >> (total - 7'(8*i) - 7'd8)) : 8'h00;
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
