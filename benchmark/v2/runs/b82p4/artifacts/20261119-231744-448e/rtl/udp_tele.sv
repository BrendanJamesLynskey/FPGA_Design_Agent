// Telemetry: period counter, one held frame (17 bytes), drop-if-held rule.
module udp_tele (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick,
    input  logic [31:0] ticks_next,   // tick count including the current tick
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    input  logic        cmd_start,
    input  logic        cmd_stop,
    input  logic [15:0] cmd_period,
    input  logic        take,
    input  logic [6:0]  tidx,
    output logic [15:0] period,
    output logic        on,
    output logic        held,
    output logic [15:0] fcnt,
    output logic [31:0] tword,
    output logic [7:0]  tlen
);
    logic [15:0] tcount, fseq;
    logic        bld, bph;
    logic [4:0]  bidx;
    logic [31:0] crc, crc_nx;
    logic [7:0]  fb [0:16];

    wire due     = tick && on && ({1'b0, tcount} + 17'd1 >= {1'b0, period});
    wire capture = due && !held;

    udp_crc32_byte u_crc (.crc(crc), .d(fb[bidx]), .nxt(crc_nx));

    // control
    always_ff @(posedge clk) begin
        if (rst) begin
            period <= 16'd100;
            on     <= 1'b0;
            tcount <= 16'd0;
            held   <= 1'b0;
            fseq   <= 16'd0;
            fcnt   <= 16'd0;
            bld    <= 1'b0;
            bph    <= 1'b0;
            bidx   <= 5'd0;
        end else begin
            if (tick && on) begin
                tcount <= due ? 16'd0 : tcount + 16'd1;
            end
            if (capture) begin
                held <= 1'b1;
                fseq <= fseq + 16'd1;
                fcnt <= fcnt + 16'd1;
                bld  <= 1'b1;
                bph  <= 1'b0;
                bidx <= 5'd0;
            end else if (bld) begin
                bidx <= bidx + 5'd1;
                if (!bph && bidx == 5'd12) begin
                    bph  <= 1'b1;
                    bidx <= 5'd0;
                end
                if (bph && bidx == 5'd3) bld <= 1'b0;
            end
            if (cmd_start) begin
                on     <= 1'b1;
                tcount <= 16'd0;
                if (cmd_period != 16'd0)
                    period <= (cmd_period < 16'd4) ? 16'd4 : cmd_period;
            end
            if (cmd_stop) begin
                on   <= 1'b0;
                held <= 1'b0;
                bld  <= 1'b0;
            end
            if (take) begin
                held <= 1'b0;
                bld  <= 1'b0;
            end
        end
    end

    // datapath (no reset: the held flag gates every read)
    always_ff @(posedge clk) begin
        if (capture) begin
            crc   <= 32'hFFFFFFFF;
            fb[0]  <= 8'hC0;
            fb[1]  <= 8'h00;
            fb[2]  <= fseq[15:8];
            fb[3]  <= fseq[7:0];
            fb[4]  <= 8'd8;
            fb[5]  <= ticks_next[31:24];
            fb[6]  <= ticks_next[23:16];
            fb[7]  <= ticks_next[15:8];
            fb[8]  <= ticks_next[7:0];
            fb[9]  <= cmds[15:8];
            fb[10] <= cmds[7:0];
            fb[11] <= refused[15:8];
            fb[12] <= refused[7:0];
        end else if (bld && !bph) begin
            crc <= crc_nx;
        end else if (bld && bph) begin
            fb[5'd13 + bidx] <= 8'((~crc) >> {bidx[1:0], 3'b000});
        end
    end

    // read side
    always_comb begin
        logic [8:0] j;
        logic [7:0] b [0:3];
        for (int k = 0; k < 4; k++) begin
            j = {tidx, 2'b00} + 9'(k);
            b[k] = (held && j < 9'd17) ? fb[j[4:0]] : 8'h00;
        end
        tword = {b[0], b[1], b[2], b[3]};
        tlen  = held ? 8'd17 : 8'd0;
    end
endmodule
