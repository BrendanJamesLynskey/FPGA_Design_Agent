// rgmii_tx.sv: GMII byte -> RGMII transmit, 10/100/1000 Mb/s, and the MAC's byte enable.
//
// 1000 Mb/s (speed 2): a byte every clock (ce always high). Data and TX_CTL leave on both edges of clk through
// ODDRE1 (rising: data[3:0] and TX_EN; falling: data[7:4] and TX_EN xor TX_ER). TXC is a 125 MHz clock made from
// clk90 (the same frequency, 90 degrees later), so its edges sit in the middle of each data half.
// 100 and 10 Mb/s (speed 1, 0): each byte goes out as two nibbles, least significant first, each held for 5 or 50
// clocks (TXD and TX_CTL the same on both edges); TXC is 25 or 2.5 MHz, low for the first half of each nibble time
// and high for the second, so its rising edge is in the middle of the nibble. ce is high on the clock the MAC must
// present its next byte (once in 10 or 100 clocks).
// TXC's waveform is formed in the clk domain and moved to clk90 through one register before its ODDRE1.
// TXC_CLK90 = 0 instead makes TXC from clk itself, through the same kind of ODDRE1 as the data, so TXC leaves
// edge-aligned with the data and the PHY's internal TX delay must be on (RGMII "-ID" mode): data and clock then share
// one clock and matched output paths, which leaves far more timing margin than a 90-degree clock on another buffer.
// Simulation uses the equivalent behaviour.

module rgmii_tx #(
    parameter int TXC_CLK90 = 1         // 1: TXC from clk90 (centred, PHY TX delay off); 0: from clk (edge-aligned)
) (
    input  logic       clk,
    input  logic       clk90,
    input  logic       rst,
    input  logic [1:0] speed,
    output logic       ce,
    input  logic [7:0] gmii_d,
    input  logic       gmii_en,
    input  logic       gmii_er,
    output logic [3:0] txd,
    output logic       tx_ctl,
    output logic       txc
);
    // nibble-time counter: n counts clocks within a nibble (0..N-1), hi selects the upper nibble
    logic [5:0] n;
    logic       hi;
    logic [5:0] nmax;
    assign nmax = (speed == 2'd1) ? 6'd4 : 6'd49;
    always_ff @(posedge clk) begin
        if (rst || speed == 2'd2) begin n <= '0; hi <= 1'b0; end
        else if (n == nmax) begin n <= '0; hi <= !hi; end
        else n <= n + 6'd1;
    end
    assign ce = (speed == 2'd2) ? 1'b1 : (n == nmax && hi);       // the byte changes after its upper nibble

    // data and control for the two edges, registered in the clk domain
    logic [3:0] d1, d2;
    logic       c1, c2;
    logic       k1, k2;                 // TXC's two half-cycles (clk domain)
    always_ff @(posedge clk) begin
        if (speed == 2'd2) begin
            d1 <= gmii_d[3:0]; d2 <= gmii_d[7:4];
            c1 <= gmii_en;     c2 <= gmii_en ^ gmii_er;
            k1 <= 1'b1;        k2 <= 1'b0;
        end else begin
            // the byte shown by the MAC changes on the clock after ce; the nibble follows hi
            d1 <= hi ? gmii_d[7:4] : gmii_d[3:0]; d2 <= hi ? gmii_d[7:4] : gmii_d[3:0];
            c1 <= gmii_en; c2 <= gmii_en ^ gmii_er;
            if (speed == 2'd1) begin                                    // 5 clocks: low 2.5, high 2.5
                k1 <= (n >= 6'd3); k2 <= (n >= 6'd2);
            end else begin                                              // 50 clocks: low 25, high 25
                k1 <= (n >= 6'd25); k2 <= (n >= 6'd25);
            end
        end
    end
    logic k1_90, k2_90, tclk;
    if (TXC_CLK90 != 0) begin : g_c90
        always_ff @(posedge clk90) begin k1_90 <= k1; k2_90 <= k2; end
        assign tclk = clk90;
    end else begin : g_c0
        assign k1_90 = k1; assign k2_90 = k2;
        assign tclk = clk;
    end
`ifdef SYNTHESIS
    for (genvar i = 0; i < 4; i++) begin : g_oddr
        ODDRE1 #(.SRVAL(1'b0)) u_oddr (.Q(txd[i]), .C(clk), .D1(d1[i]), .D2(d2[i]), .SR(1'b0));
    end
    ODDRE1 #(.SRVAL(1'b0)) u_ctl (.Q(tx_ctl), .C(clk), .D1(c1), .D2(c2), .SR(1'b0));
    ODDRE1 #(.SRVAL(1'b0)) u_txc (.Q(txc), .C(tclk), .D1(k1_90), .D2(k2_90), .SR(1'b0));
`else
    // ODDRE1 behaviour: D1 and D2 are taken at the rising edge; D1 drives the output from that edge, D2 from the
    // falling edge (registered, so the output never glitches at an edge)
    logic [3:0] d2h;
    logic       c2h, k2h;
    always @(posedge clk or negedge clk) begin
        if (clk) begin txd <= d1; tx_ctl <= c1; d2h <= d2; c2h <= c2; end
        else     begin txd <= d2h; tx_ctl <= c2h; end
    end
    always @(posedge tclk or negedge tclk) begin
        if (tclk) begin txc <= k1_90; k2h <= k2_90; end
        else       txc <= k2h;
    end
`endif
endmodule
