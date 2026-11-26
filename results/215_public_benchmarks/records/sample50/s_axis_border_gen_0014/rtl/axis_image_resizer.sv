module axis_image_resizer #
(
    parameter IMG_WIDTH_IN  = 640,
    parameter IMG_HEIGHT_IN = 480,
    parameter IMG_WIDTH_OUT = 320,
    parameter IMG_HEIGHT_OUT = 240,
    parameter DATA_WIDTH    = 16
)
(
    input  wire                  clk,
    input  wire                  resetn,
    input  wire [DATA_WIDTH-1:0] s_axis_tdata,
    input  wire                  s_axis_tvalid,
    output wire                  s_axis_tready,
    input  wire                  s_axis_tlast,
    input  wire                  s_axis_tuser,

    output reg [DATA_WIDTH-1:0]  m_axis_tdata,
    output reg                   m_axis_tvalid,
    input  wire                  m_axis_tready,
    output reg                   m_axis_tlast,
    output reg                   m_axis_tuser
);

    localparam X_SCALE = IMG_WIDTH_IN / IMG_WIDTH_OUT;
    localparam Y_SCALE = IMG_HEIGHT_IN / IMG_HEIGHT_OUT;

    // x_count_in / y_count_in are kept as phase counters (index modulo scale)
    reg [15:0] x_count_in, y_count_in;
    reg [15:0] x_count_out;
    reg [15:0] y_row_in;   // input row index, wraps at IMG_HEIGHT_IN

    assign s_axis_tready = m_axis_tready;

    wire x_hit = (x_count_in == 16'd0);
    wire y_hit = (y_count_in == 16'd0);
    wire fwd   = x_hit && y_hit;

    always @(posedge clk) begin
        if (!resetn) begin
            x_count_in    <= 16'd0;
            y_count_in    <= 16'd0;
            y_row_in      <= 16'd0;
            x_count_out   <= 16'd0;
            m_axis_tvalid <= 1'b0;
            m_axis_tlast  <= 1'b0;
            m_axis_tuser  <= 1'b0;
            m_axis_tdata  <= {DATA_WIDTH{1'b0}};
        end else if (s_axis_tready) begin
            m_axis_tvalid <= 1'b0;
            if (s_axis_tvalid) begin
                if (fwd) begin
                    m_axis_tvalid <= 1'b1;
                    m_axis_tdata  <= s_axis_tdata;
                    m_axis_tlast  <= (x_count_out == IMG_WIDTH_OUT - 1);
                    m_axis_tuser  <= s_axis_tuser;
                    x_count_out   <= (x_count_out == IMG_WIDTH_OUT - 1) ? 16'd0 : x_count_out + 16'd1;
                end
                if (s_axis_tlast) begin
                    x_count_in  <= 16'd0;
                    x_count_out <= 16'd0;
                    if (y_row_in == IMG_HEIGHT_IN - 1) begin
                        y_row_in   <= 16'd0;
                        y_count_in <= 16'd0;
                    end else begin
                        y_row_in   <= y_row_in + 16'd1;
                        y_count_in <= (y_count_in == Y_SCALE - 1) ? 16'd0 : y_count_in + 16'd1;
                    end
                end else begin
                    x_count_in <= (x_count_in == X_SCALE - 1) ? 16'd0 : x_count_in + 16'd1;
                end
            end
        end
    end

endmodule
