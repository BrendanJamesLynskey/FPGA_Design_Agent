// udp_telem: tick generator, uptime counter, telemetry pacer, held frame (17 bytes) and frame counters.
module udp_telem (
    input  logic        clk,
    input  logic        rst,
    input  logic        wr_tick,
    input  logic [7:0]  tick_n,
    input  logic        take,
    input  logic        cmd_start,
    input  logic [15:0] cmd_period,
    input  logic        cmd_stop,
    input  logic [15:0] cnt_ok16,
    input  logic [15:0] refused16,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] ticks,
    output logic [15:0] fcount,
    output logic [7:0]  tlen,
    input  logic [6:0]  tidx,
    output logic [31:0] tword
);
    logic [7:0]  pending;
    logic [15:0] tcount;
    logic [15:0] fseq;
    logic        held;

    logic        tk;
    logic [16:0] tcount_n;
    logic [31:0] ticks_n;
    logic        due, acc, fr_clr;

    assign tk       = (pending != 8'd0);
    assign tcount_n = {1'b0, tcount} + 17'd1;
    assign ticks_n  = ticks + 32'd1;
    assign due      = tk && tel_on && (tcount_n >= {1'b0, period});
    assign fr_clr   = take || cmd_stop;
    assign acc      = due && !held && !fr_clr;

    always_ff @(posedge clk) begin
        if (rst) begin
            pending <= 8'd0;
            ticks   <= 32'd0;
            tcount  <= 16'd0;
            tel_on  <= 1'b0;
            period  <= 16'd100;
            fseq    <= 16'd0;
            fcount  <= 16'd0;
            held    <= 1'b0;
        end else begin
            if (wr_tick)  pending <= tick_n;
            else if (tk)  pending <= pending - 8'd1;
            if (tk) ticks <= ticks_n;
            if (tk && tel_on) tcount <= due ? 16'd0 : tcount_n[15:0];
            if (acc) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
            end
            if (fr_clr) held <= 1'b0;
            if (cmd_start) begin
                if (cmd_period != 16'd0) period <= (cmd_period < 16'd4) ? 16'd4 : cmd_period;
                tel_on <= 1'b1;
                tcount <= 16'd0;
            end
            if (cmd_stop) tel_on <= 1'b0;
        end
    end

    logic [135:0] pay;
    always_comb begin
        pay = 136'd0;
        pay[63:0] = {refused16[7:0], refused16[15:8], cnt_ok16[7:0], cnt_ok16[15:8],
                     ticks_n[7:0], ticks_n[15:8], ticks_n[23:16], ticks_n[31:24]};
    end

    logic busy_unused;
    udp_reply u_frame (
        .clk(clk), .rst(rst), .start(acc), .clr(fr_clr),
        .hdr0(8'hC0), .hdr1(8'h00), .seq(fseq), .plen(5'd8), .payload(pay),
        .busy(busy_unused), .len(tlen), .rd_idx(tidx), .rd_word(tword));
endmodule
