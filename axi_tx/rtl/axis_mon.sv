// axis_mon: passive performance and coverage counters for one AXI4-Stream interface (brief 59A). 32-bit, saturating.
// Read-out by index (rd_sel, valid the cycle after it changes):
//   0 cycles out of reset   1 beats   2 packets (TLAST beats)   3 stall cycles (TVALID high, TREADY low)   4 idle cycles
//   5-9 READY-wait bins per beat: 0, 1, 2-3, 4-15, 16+ cycles     10-14 packet length bins: 1, 2-3, 4-7, 8-15, 16+ beats
//   15 .. 15+KW  last-beat TKEEP: number of ones (0 .. KW)         16+KW longest packet (beats)
module axis_mon #(
    parameter int DATA_W = 32
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic                clear,
    input  logic [DATA_W/8-1:0] tkeep,
    input  logic                tlast,
    input  logic                tvalid,
    input  logic                tready,
    input  logic [5:0]          rd_sel,
    output logic [31:0]         rd_data
);
    localparam int KW = DATA_W / 8;
    localparam int NC = 17 + KW;
    logic [31:0] cnt [NC];
    logic [4:0]  wait_c = '0;
    logic [15:0] beats = '0;                    // beats of the current packet already transferred
    wire hs = tvalid && tready;

    function automatic logic [2:0] wbin(input logic [4:0] w);
        if (w == 0) wbin = 3'd0; else if (w == 1) wbin = 3'd1; else if (w < 4) wbin = 3'd2;
        else if (w < 16) wbin = 3'd3; else wbin = 3'd4;
    endfunction
    function automatic logic [2:0] pbin(input logic [15:0] n);   // n = packet length in beats (>= 1)
        if (n <= 1) pbin = 3'd0; else if (n < 4) pbin = 3'd1; else if (n < 8) pbin = 3'd2; else if (n < 16) pbin = 3'd3;
        else pbin = 3'd4;
    endfunction
    function automatic int ones(input logic [KW-1:0] k);
        ones = 0;
        for (int i = 0; i < KW; i++) ones = ones + int'(k[i]);
    endfunction

    wire [15:0] plen = beats + 1'b1;
    logic [NC-1:0] inc;
    always_comb begin
        inc = '0;
        inc[0] = 1'b1;
        if (hs) begin inc[1] = 1'b1; inc[5 + 32'(wbin(wait_c))] = 1'b1; end
        if (hs && tlast) begin inc[2] = 1'b1; inc[10 + 32'(pbin(plen))] = 1'b1; inc[15 + ones(tkeep)] = 1'b1; end
        if (tvalid && !tready) inc[3] = 1'b1;
        if (!tvalid) inc[4] = 1'b1;
    end

    initial for (int i = 0; i < NC; i++) cnt[i] = '0;
    always_ff @(posedge aclk) begin
        if (clear) begin
            for (int i = 0; i < NC; i++) cnt[i] <= '0;
            wait_c <= '0; beats <= '0;
        end else if (aresetn) begin
            for (int i = 0; i < NC - 1; i++) if (inc[i] && cnt[i] != 32'hFFFF_FFFF) cnt[i] <= cnt[i] + 1'b1;
            if (hs && tlast && 32'(plen) > cnt[NC-1]) cnt[NC-1] <= 32'(plen);
            if (hs || !tvalid) wait_c <= '0; else if (wait_c != 5'h1F) wait_c <= wait_c + 1'b1;
            if (hs) beats <= tlast ? 16'd0 : (beats == 16'hFFFF ? beats : beats + 1'b1);
        end else begin
            wait_c <= '0; beats <= '0;
        end
    end
    always_ff @(posedge aclk) rd_data <= (rd_sel < 6'(NC)) ? cnt[rd_sel[$clog2(NC)-1:0]] : 32'h0;
endmodule
