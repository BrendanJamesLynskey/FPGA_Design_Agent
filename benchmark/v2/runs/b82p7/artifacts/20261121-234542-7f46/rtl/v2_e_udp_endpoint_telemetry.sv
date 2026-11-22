// Telemetry: uptime tick counter, period count, one held frame (built serially,
// CRC one byte per clock), frame sequence and frame count.
module v2_e_udp_endpoint_telemetry (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic        tick,
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    input  logic        start_en,
    input  logic [15:0] start_per,
    input  logic        stop_en,
    input  logic        take,
    input  logic [6:0]  tidx,
    output logic        on,
    output logic        held,
    output logic [15:0] period,
    output logic [31:0] uptime,
    output logic [15:0] fcount,
    output logic [4:0]  tlen,
    output logic [31:0] tword
);
    logic [15:0] pcount, fseq;
    logic [16:0] pc_n;
    logic [31:0] up_n;
    logic        due, held_c;

    logic [15:0] s_seq, s_cmds, s_ref;
    logic [31:0] s_tick, fcrc, fcrc_nx;
    logic        fb_act;
    logic [3:0]  fb_i;

    assign up_n   = uptime + 32'd1;
    assign pc_n   = {1'b0, pcount} + 17'd1;
    assign due    = tick && on && (pc_n >= {1'b0, period});
    assign held_c = held && !take && !stop_en;

    // frame image, byte 0 on top (bytes 17..19 zero)
    logic [159:0] fimg;
    assign fimg = {8'hC0, 8'h00, s_seq, 8'h08, s_tick, s_cmds, s_ref,
                   ~fcrc[7:0], ~fcrc[15:8], ~fcrc[23:16], ~fcrc[31:24],
                   24'd0};

    function automatic logic [7:0] fbyte(input logic [159:0] img, input logic [4:0] i);
        fbyte = 8'(img >> (8 * (19 - {27'd0, i})));
    endfunction

    v2_e_udp_endpoint_crc32_byte u_crc (
        .crc_in(fcrc), .data(fbyte(fimg, {1'b0, fb_i})), .crc_out(fcrc_nx));

    // control state
    always_ff @(posedge clk) begin
        if (rst) begin
            on     <= 1'b0;
            held   <= 1'b0;
            period <= 16'd100;
            uptime <= 32'd0;
            pcount <= 16'd0;
            fseq   <= 16'd0;
            fcount <= 16'd0;
            fb_act <= 1'b0;
            fb_i   <= 4'd0;
        end else begin
            if (tick) begin
                uptime <= up_n;
                if (on) pcount <= due ? 16'd0 : pc_n[15:0];
            end
            if (start_en) begin
                on     <= 1'b1;
                pcount <= 16'd0;
                if (start_per != 16'd0) period <= (start_per < 16'd4) ? 16'd4 : start_per;
            end
            if (stop_en) on <= 1'b0;
            held <= held_c;
            if (due && !held_c) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
                fb_act <= 1'b1;
                fb_i   <= 4'd0;
            end else if (fb_act) begin
                if (fb_i == 4'd12) fb_act <= 1'b0;
                else fb_i <= fb_i + 4'd1;
            end
        end
    end

    // datapath (no reset): snapshot and CRC
    always_ff @(posedge clk) begin
        if (due && !held_c) begin
            s_seq  <= fseq;
            s_tick <= up_n;
            s_cmds <= cmds;
            s_ref  <= refused;
            fcrc   <= 32'hFFFFFFFF;
        end else if (fb_act) begin
            fcrc <= fcrc_nx;
        end
    end

    assign tlen = held ? 5'd17 : 5'd0;

    logic [8:0] tbase;
    logic [8:0] ti0, ti1, ti2, ti3;
    assign tbase = {tidx, 2'b00};
    assign ti0 = tbase;
    assign ti1 = tbase + 9'd1;
    assign ti2 = tbase + 9'd2;
    assign ti3 = tbase + 9'd3;
    assign tword = {
        (held && ti0 < 9'd17) ? fbyte(fimg, ti0[4:0]) : 8'h00,
        (held && ti1 < 9'd17) ? fbyte(fimg, ti1[4:0]) : 8'h00,
        (held && ti2 < 9'd17) ? fbyte(fimg, ti2[4:0]) : 8'h00,
        (held && ti3 < 9'd17) ? fbyte(fimg, ti3[4:0]) : 8'h00
    };
endmodule
