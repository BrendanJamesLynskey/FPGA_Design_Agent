// lat_hist.sv: a latency histogram in block RAM, with count, sum, minimum and maximum (brief 58A step 6).
//
// Each sample (s_v, s_val in clocks) adds one to bin s_val >> SHIFT; values beyond the last bin go to the last bin
// (the overflow bin) and are still exact in min/max/sum. A sample takes two clocks (read, then write); samples closer
// than that are counted in `lost` and left out (one order per trigger frame keeps samples far apart). clear zeroes
// every bin, one a clock, and the statistics.

module lat_hist #(
    parameter int NB    = 256,          // bins, a power of two
    parameter int SHIFT = 0             // bin width = 2**SHIFT clocks
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clear,
    input  logic        s_v,
    input  logic [31:0] s_val,
    input  logic [$clog2(NB)-1:0] h_bin,
    output logic [31:0] h_q,
    output logic [31:0] count,
    output logic [47:0] sum,
    output logic [31:0] vmin,
    output logic [31:0] vmax,
    output logic [31:0] lost,
    output logic        busy
);
    localparam int AW = $clog2(NB);
    initial begin
        if ((1 << AW) != NB || NB < 2) $error("lat_hist: NB must be a power of two (got %0d)", NB);
    end
    // plain RAM ports (one write, two registered reads) so that it maps to block RAM
    (* ram_style = "block" *) logic [31:0] mem [NB];
    logic [AW:0]   ca;
    logic          p1;
    logic [AW-1:0] a1, ra;
    logic [31:0]   q1;
    logic          we;
    logic [AW-1:0] wa;
    logic [31:0]   wd;
    assign busy = !ca[AW];

    logic [31:0] sh;
    assign sh = s_val >> SHIFT;
    assign ra = (sh >= 32'(NB)) ? AW'(NB - 1) : sh[AW-1:0];
    assign we = busy || p1;
    assign wa = busy ? ca[AW-1:0] : a1;
    assign wd = busy ? 32'd0 : q1 + 32'd1;
    // port A: the write (clearing, or the increment one clock after a sample) or else the sample's read (a sample in
    // the increment's clock is counted lost, so the two never need the port at once); port B: the host
    logic [AW-1:0] aa;
    assign aa = we ? wa : ra;
    always_ff @(posedge clk) begin
        if (we) mem[aa] <= wd;
        else    q1 <= mem[aa];
    end
    always_ff @(posedge clk) h_q <= mem[h_bin];

    always_ff @(posedge clk) begin
        if (rst) begin
            ca <= '0; p1 <= 1'b0; a1 <= '0;
            count <= '0; sum <= '0; vmin <= '1; vmax <= '0; lost <= '0;
        end else if (busy) begin
            ca <= ca + 1'b1;
            p1 <= 1'b0;
        end else if (clear) begin
            ca <= '0; count <= '0; sum <= '0; vmin <= '1; vmax <= '0; lost <= '0; p1 <= 1'b0;
        end else begin
            p1 <= 1'b0;
            if (s_v) begin
                if (p1) lost <= lost + 32'd1;
                else begin
                    p1 <= 1'b1;
                    a1 <= ra;
                    count <= count + 32'd1;
                    sum   <= sum + {16'h0, s_val};
                    if (s_val < vmin) vmin <= s_val;
                    if (s_val > vmax) vmax <= s_val;
                end
            end
        end
    end
endmodule
