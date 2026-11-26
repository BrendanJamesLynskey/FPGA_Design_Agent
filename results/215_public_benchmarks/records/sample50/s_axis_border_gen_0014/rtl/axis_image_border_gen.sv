`timescale 1ps / 1ps

module axis_image_border_gen #
(
    parameter IMG_WIDTH  = 336,
    parameter IMG_HEIGHT = 256,
    parameter BORDER_COLOR = 16'hFFFF,
    parameter DATA_MASK    = 16'h0000   // unused
)
(
    input  wire            clk,
    input  wire            resetn,

    input  wire [15:0]     s_axis_tdata,
    input  wire            s_axis_tvalid,
    output wire            s_axis_tready,
    input  wire            s_axis_tlast,
    input  wire            s_axis_tuser,

    output wire [15:0]     m_axis_tdata,
    output wire            m_axis_tvalid,
    input  wire            m_axis_tready,
    output wire            m_axis_tlast,
    output wire            m_axis_tuser
);

    reg [15:0] x_count_r, y_count_r;

    // While resetn is low the counters read as 0 (the registers clear at the
    // next clock edge, synchronously).
    wire [15:0] x_count = resetn ? x_count_r : 16'd0;
    wire [15:0] y_count = resetn ? y_count_r : 16'd0;

    wire is_top_row      = (y_count == 16'd0);
    wire is_bottom_row   = (y_count == IMG_HEIGHT + 1);
    wire is_left_border  = (x_count == 16'd0);
    wire is_right_border = (x_count == IMG_WIDTH + 1);
    wire is_border_pixel = is_top_row || is_bottom_row || is_left_border || is_right_border;

    assign m_axis_tdata  = is_border_pixel ? BORDER_COLOR[15:0] : s_axis_tdata;
    assign m_axis_tvalid = is_border_pixel ? 1'b1 : s_axis_tvalid;
    assign m_axis_tlast  = is_right_border;
    assign m_axis_tuser  = is_left_border && is_top_row;
    assign s_axis_tready = !is_border_pixel && m_axis_tready;

    always @(posedge clk) begin
        if (!resetn) begin
            x_count_r <= 16'd0;
            y_count_r <= 16'd0;
        end else if (m_axis_tvalid && m_axis_tready) begin
            if (is_right_border) begin
                x_count_r <= 16'd0;
                y_count_r <= is_bottom_row ? 16'd0 : y_count_r + 16'd1;
            end else begin
                x_count_r <= x_count_r + 16'd1;
            end
        end
    end

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused = &{1'b0, s_axis_tlast, s_axis_tuser, DATA_MASK[0]};
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
