// sprite_regs.sv: sprite rows, position, colours, CTRL (with the bounce
// update at each frame wrap) and FRAME, in the shell window.
module sprite_regs (
    input  logic              clk,
    input  logic              rst,
    input  logic              frame_tick,
    output logic [255:0]      rows,
    output logic [9:0]        sx,
    output logic [9:0]        sy,
    output logic [11:0]       sprite_color,
    output logic [11:0]       bg_color,
    output logic              en,
    input  logic [6:0]        win_addr,
    input  logic              win_wr,
    input  logic              win_rd,
    input  logic [31:0]       win_wdata,
    output logic [31:0]       win_rdata
);
    localparam logic [9:0] XMAX = 10'd624, YMAX = 10'd464;
    logic [3:0]  ctrl;
    logic [15:0] row_r [16];

    always_comb for (int i = 0; i < 16; i++) rows[16 * i +: 16] = row_r[i];
    logic [31:0] frame;

    assign en = ctrl[0];

    wire wr_x = win_wr && win_addr == 7'h10;
    wire wr_y = win_wr && win_addr == 7'h11;
    wire wr_c = win_wr && win_addr == 7'h14;
    wire move = frame_tick && ctrl[1];

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 16; i++) row_r[i] <= '0;
            sx <= '0; sy <= '0; sprite_color <= 12'hFFF; bg_color <= 12'h000;
            ctrl <= 4'b0001; frame <= '0;
        end else begin
            if (frame_tick) frame <= frame + 1'b1;
            if (win_wr && win_addr < 7'h10) row_r[win_addr[3:0]] <= win_wdata[15:0];
            if (win_wr && win_addr == 7'h12) sprite_color <= win_wdata[11:0];
            if (win_wr && win_addr == 7'h13) bg_color <= win_wdata[11:0];
            // horizontal
            if (wr_x) sx <= win_wdata[9:0];
            else if (move) begin
                if (!ctrl[2] && sx >= XMAX)      sx <= sx - 1'b1;
                else if (ctrl[2] && sx == '0)    sx <= sx + 1'b1;
                else if (ctrl[2])                sx <= sx - 1'b1;
                else                             sx <= sx + 1'b1;
            end
            // vertical
            if (wr_y) sy <= win_wdata[9:0];
            else if (move) begin
                if (!ctrl[3] && sy >= YMAX)      sy <= sy - 1'b1;
                else if (ctrl[3] && sy == '0)    sy <= sy + 1'b1;
                else if (ctrl[3])                sy <= sy - 1'b1;
                else                             sy <= sy + 1'b1;
            end
            // CTRL: direction bits flip at the edges
            if (wr_c) ctrl <= win_wdata[3:0];
            else if (move) begin
                if (!ctrl[2] && sx >= XMAX) ctrl[2] <= 1'b1;
                else if (ctrl[2] && sx == '0) ctrl[2] <= 1'b0;
                if (!ctrl[3] && sy >= YMAX) ctrl[3] <= 1'b1;
                else if (ctrl[3] && sy == '0) ctrl[3] <= 1'b0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            if (win_addr < 7'h10) win_rdata <= {16'd0, row_r[win_addr[3:0]]};
            else case (win_addr)
                7'h10:   win_rdata <= {22'd0, sx};
                7'h11:   win_rdata <= {22'd0, sy};
                7'h12:   win_rdata <= {20'd0, sprite_color};
                7'h13:   win_rdata <= {20'd0, bg_color};
                7'h14:   win_rdata <= {28'd0, ctrl};
                7'h15:   win_rdata <= frame;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
