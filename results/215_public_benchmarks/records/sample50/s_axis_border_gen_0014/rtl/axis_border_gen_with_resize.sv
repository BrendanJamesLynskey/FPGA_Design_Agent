`timescale 1ps / 1ps

/* verilator lint_off DECLFILENAME */
module axis_image_border_gen_with_resizer #(
    parameter IMG_WIDTH_IN   = 640,
    parameter IMG_HEIGHT_IN  = 480,
    parameter IMG_WIDTH_OUT  = 320,
    parameter IMG_HEIGHT_OUT = 240,
    parameter BORDER_COLOR   = 16'hFFFF,
    parameter DATA_WIDTH     = 16,
    // informational: the resizer derives its own scale factors
    /* verilator lint_off UNUSEDPARAM */
    parameter X_SCALE        = IMG_WIDTH_IN / IMG_WIDTH_OUT,
    parameter Y_SCALE        = IMG_HEIGHT_IN / IMG_HEIGHT_OUT
    /* verilator lint_on UNUSEDPARAM */
)(
    input  wire                  clk,
    input  wire                  resetn,
    input  wire [DATA_WIDTH-1:0] s_axis_tdata,
    input  wire                  s_axis_tvalid,
    output wire                  s_axis_tready,
    input  wire                  s_axis_tlast,
    input  wire                  s_axis_tuser,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire                  m_axis_tvalid,
    input  wire                  m_axis_tready,
    output wire                  m_axis_tlast,
    output wire                  m_axis_tuser
);

    wire [DATA_WIDTH-1:0] r_tdata;
    wire                  r_tvalid, r_tready, r_tlast, r_tuser;

    axis_image_resizer #(
        .IMG_WIDTH_IN(IMG_WIDTH_IN), .IMG_HEIGHT_IN(IMG_HEIGHT_IN),
        .IMG_WIDTH_OUT(IMG_WIDTH_OUT), .IMG_HEIGHT_OUT(IMG_HEIGHT_OUT),
        .DATA_WIDTH(DATA_WIDTH)
    ) u_resizer (
        .clk(clk), .resetn(resetn),
        .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready), .s_axis_tlast(s_axis_tlast),
        .s_axis_tuser(s_axis_tuser),
        .m_axis_tdata(r_tdata), .m_axis_tvalid(r_tvalid),
        .m_axis_tready(r_tready), .m_axis_tlast(r_tlast),
        .m_axis_tuser(r_tuser)
    );

    axis_image_border_gen #(
        .IMG_WIDTH(IMG_WIDTH_OUT), .IMG_HEIGHT(IMG_HEIGHT_OUT),
        .BORDER_COLOR(BORDER_COLOR)
    ) u_border (
        .clk(clk), .resetn(resetn),
        .s_axis_tdata(r_tdata), .s_axis_tvalid(r_tvalid),
        .s_axis_tready(r_tready), .s_axis_tlast(r_tlast),
        .s_axis_tuser(r_tuser),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast),
        .m_axis_tuser(m_axis_tuser)
    );

endmodule
/* verilator lint_on DECLFILENAME */
