// Fixture for the contract-test generator (brief 27B P0): a full-raster stream delayed by DEPTH clocks, no
// back-pressure (tready is always 1). MUT: 4 drops tready now and then, 5 adds a clock of latency, 6 makes tdata a
// bit narrower than the contract.
module fx_video_delay #(
    parameter int DEPTH = 7,
    parameter int LINE  = 12,
    parameter int MUT   = 0
) (
    input  logic                           clk,
    input  logic                           rst,
    input  logic                           s_axis_video_tvalid,
    output logic                           s_axis_video_tready,
    input  logic [23:0]                    s_axis_video_tdata,
    input  logic [2:0]                     s_axis_video_tuser,
    input  logic                           s_axis_video_tlast,
    output logic                           m_axis_video_tvalid,
    input  logic                           m_axis_video_tready,
    output logic [(MUT == 6 ? 22 : 23):0]  m_axis_video_tdata,
    output logic [2:0]                     m_axis_video_tuser,
    output logic                           m_axis_video_tlast
);
    localparam int D = (MUT == 5) ? DEPTH + 1 : DEPTH;
    logic [28:0] pipe [D];
    logic [3:0]  cnt;
    always_ff @(posedge clk) begin
        if (rst) cnt <= '0; else cnt <= cnt + 1;
    end
    assign s_axis_video_tready = (MUT == 4) ? (cnt != 4'd9) : 1'b1;
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < D; i++) pipe[i] <= '0;
        end else begin
            pipe[0] <= {s_axis_video_tvalid, s_axis_video_tlast, s_axis_video_tuser, s_axis_video_tdata};
            for (int i = 1; i < D; i++) pipe[i] <= pipe[i-1];
        end
    end
    assign m_axis_video_tvalid = pipe[D-1][28];
    assign m_axis_video_tlast  = pipe[D-1][27];
    assign m_axis_video_tuser  = pipe[D-1][26:24];
    assign m_axis_video_tdata  = pipe[D-1][(MUT == 6 ? 22 : 23):0];
endmodule
