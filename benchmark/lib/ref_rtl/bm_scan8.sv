// bm_scan8.sv: eight-digit multiplexed display. Digit k (0 = rightmost, AN[0])
// is lit for 2^REFRESH_BITS clocks, in order 0..7. While digit k is lit its
// anode is low unless blank[k] is set (then every anode stays high for that
// slot). seg is active-low {g,f,e,d,c,b,a}; dp_n is active low.
module bm_scan8 #(
    parameter int REFRESH_BITS = 17
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        enable,
    input  logic [7:0][6:0] seg_lit,    // per digit k: seg_lit[k]: 1 = segment lit, bit 0 = a
    input  logic [7:0]  blank,
    input  logic [7:0]  dp_lit,
    output logic [7:0]  an,
    output logic [6:0]  seg_n,
    output logic        dp_n
);
    logic [REFRESH_BITS+2:0] t;
    logic [2:0] k;
    assign k = t[REFRESH_BITS+2:REFRESH_BITS];

    always_ff @(posedge clk) begin
        if (rst) begin
            t     <= '0;
            an    <= 8'hFF;
            seg_n <= 7'h7F;
            dp_n  <= 1'b1;
        end else begin
            t     <= t + 1'b1;
            an    <= (enable && !blank[k]) ? ~(8'b1 << k) : 8'hFF;
            seg_n <= ~seg_lit[k];
            dp_n  <= ~dp_lit[k];
        end
    end
endmodule
