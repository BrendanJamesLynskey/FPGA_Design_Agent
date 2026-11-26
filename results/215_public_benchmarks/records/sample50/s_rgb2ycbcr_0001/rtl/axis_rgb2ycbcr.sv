// AXI-Stream RGB565 -> YCbCr (5:6:5) converter with a small output FIFO.
// Conversion is combinational on the accepted beat and written straight into the FIFO.
// The FIFO is fixed at 16 entries (4-bit pointers); PIXEL_WIDTH/FIFO_DEPTH are kept for the interface.
/* verilator lint_off UNUSEDPARAM */
module axis_rgb2ycbcr #(
    parameter PIXEL_WIDTH = 16,
    parameter FIFO_DEPTH  = 16
)(
/* verilator lint_on UNUSEDPARAM */
    input  wire            aclk,
    input  wire            aresetn,

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

    wire rst = !aresetn;

    // 18-bit FIFO words: {tuser, tlast, data[15:0]}
    reg [17:0] fifo_mem [0:15];

    reg [3:0] write_ptr;
    reg [3:0] read_ptr;

    wire empty = (read_ptr == write_ptr);
    wire full  = ((write_ptr + 4'd1) == read_ptr);

    wire fifo_write = s_axis_tvalid && !full;
    wire fifo_read  = !empty && m_axis_tready;

    // RGB565 -> 8 bit
    wire [7:0] r = {s_axis_tdata[15:11], 3'b0};
    wire [7:0] g = {s_axis_tdata[10:5],  2'b0};
    wire [7:0] b = {s_axis_tdata[4:0],   3'b0};

    wire signed [17:0] rs = {10'b0, r};
    wire signed [17:0] gs = {10'b0, g};
    wire signed [17:0] bs = {10'b0, b};

    wire signed [17:0] y_s  = 18'sd77 * rs + 18'sd150 * gs + 18'sd29 * bs;
    wire signed [17:0] cb_s = -18'sd43 * rs - 18'sd85 * gs + 18'sd128 * bs;
    wire signed [17:0] cr_s = 18'sd128 * rs - 18'sd107 * gs - 18'sd21 * bs;

    // only the bits kept in the FIFO word are formed
    wire [4:0] y5  = y_s[15:11]  + 5'd2;   // (y>>8)+16, top 5 bits: +16 = +2 in bits [7:3]
    wire [5:0] cb6 = cb_s[15:10] + 6'd32;  // +128 = +32 in bits [7:2]
    wire [4:0] cr5 = cr_s[15:11] + 5'd16;  // +128 = +16 in bits [7:3]

    wire [15:0] word = {y5, cb6, cr5};

    always @(posedge aclk) begin
        if (fifo_write)
            fifo_mem[write_ptr] <= {s_axis_tuser, s_axis_tlast, word};
    end

    always @(posedge aclk) begin
        if (rst) begin
            write_ptr <= 4'd0;
            read_ptr  <= 4'd0;
        end else begin
            if (fifo_write) write_ptr <= write_ptr + 4'd1;
            if (fifo_read)  read_ptr  <= read_ptr + 4'd1;
        end
    end

    wire [17:0] rd_word = fifo_mem[read_ptr];

    assign s_axis_tready = !full;
    assign m_axis_tvalid = !empty;
    assign m_axis_tdata  = rd_word[15:0];
    assign m_axis_tlast  = rd_word[16];
    assign m_axis_tuser  = rd_word[17];

    // unused sum bits
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_ok = &{1'b0, y_s[17:16], y_s[10:0], cb_s[17:16], cb_s[9:0], cr_s[17:16], cr_s[10:0]};
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
