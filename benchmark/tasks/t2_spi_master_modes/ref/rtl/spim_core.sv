// spim_core.sv: SPI master frame engine. Edges at t = k*div (k = 1..2N) after
// the frame starts; frame end at t = (2N+1)*div. Modes by cpol/cpha; 8 or 16
// bits; MSB or LSB first. All outputs registered.
module spim_core (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,      // one clock, ignored while busy
    input  logic [15:0] txd,
    input  logic [15:0] div,
    input  logic        cpol,       // live value: idle level and frame setting
    input  logic        cpha,
    input  logic        lsb,
    input  logic        w16,
    input  logic        cs_hold,    // live value
    input  logic        miso,       // synchronous
    output logic        busy,
    output logic        done,       // one-clock pulse at frame end
    output logic [15:0] rxd,
    output logic        cs_n,
    output logic        sclk,
    output logic        mosi
);
    logic        c_pol, c_pha, c_lsb, c_w16;
    logic [15:0] dv, cnt, tx, rx;
    logic [5:0]  k;                 // edges done so far
    logic [4:0]  nb;

    // bit i of the frame in transmit order
    function automatic logic bit_at(input logic [15:0] d, input logic [4:0] n, input logic l, input logic [4:0] i);
        bit_at = l ? d[i[3:0]] : d[4'(n - 5'd1 - i)];
    endfunction

    logic [5:0] e;                  // the edge about to happen
    assign e = k + 6'd1;

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            busy <= 1'b0; cs_n <= 1'b1; sclk <= 1'b0; mosi <= 1'b0; rxd <= '0;
            c_pol <= 1'b0; c_pha <= 1'b0; c_lsb <= 1'b0; c_w16 <= 1'b0;
            dv <= '0; cnt <= '0; tx <= '0; rx <= '0; k <= '0; nb <= '0;
        end else if (!busy) begin
            sclk <= cpol;
            mosi <= 1'b0;
            if (!cs_hold) cs_n <= 1'b1;
            if (start) begin
                busy  <= 1'b1;
                cs_n  <= 1'b0;
                c_pol <= cpol; c_pha <= cpha; c_lsb <= lsb; c_w16 <= w16;
                dv    <= div;
                cnt   <= div - 1'b1;
                tx    <= txd;
                rx    <= '0;
                k     <= '0;
                nb    <= w16 ? 5'd16 : 5'd8;
                mosi  <= cpha ? 1'b0 : bit_at(txd, w16 ? 5'd16 : 5'd8, lsb, 5'd0);
            end
        end else if (cnt != '0) begin
            cnt <= cnt - 1'b1;
        end else begin
            cnt <= dv - 1'b1;
            k   <= e;
            if (k == {nb, 1'b0}) begin                       // end slot: no edge
                busy <= 1'b0;
                done <= 1'b1;
                rxd  <= rx;
                mosi <= 1'b0;
                if (!cs_hold) cs_n <= 1'b1;
            end else begin
                sclk <= ~sclk;
                if (e[0] != c_pha) begin                       // sample edge
                    // index of the bit sampled: CPHA 0 -> (e-1)/2, CPHA 1 -> e/2 - 1; both = (e-1) >> 1
                    if (c_lsb) rx[4'((e - 6'd1) >> 1)] <= miso;
                    else       rx[4'(nb - 5'd1 - 5'((e - 6'd1) >> 1))] <= miso;
                end else if (c_pha) begin                      // CPHA 1: leading edge 2i+1 puts out bit i
                    mosi <= bit_at(tx, nb, c_lsb, 5'((e - 6'd1) >> 1));
                end else if (e != {nb, 1'b0}) begin            // CPHA 0: trailing edge 2i puts out bit i
                    mosi <= bit_at(tx, nb, c_lsb, 5'(e >> 1));
                end
            end
        end
    end
endmodule
