// axis_checker: the AXI4-Stream rule monitor and its log as one block for any stream (brief 59A): axis_rules + axi_viol_log.
module axis_checker #(
    parameter int DATA_W = 32
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic                clear,
    input  logic [4:0]          en,
    input  logic [31:0]         now,
    input  logic [15:0]         maxlen,
    input  logic [DATA_W-1:0]   tdata,
    input  logic [DATA_W/8-1:0] tkeep,
    input  logic [DATA_W/8-1:0] tstrb,
    input  logic                tlast,
    input  logic                tvalid,
    input  logic                tready,
    output logic [4:0]          viol,
    output logic                trig,
    output logic                any,
    input  logic [5:0]          rd_sel,
    output logic [31:0]         rd_data
);
    axis_rules #(.DATA_W(DATA_W)) u_rules (.aclk(aclk), .aresetn(aresetn), .maxlen(maxlen), .tdata(tdata), .tkeep(tkeep),
                                           .tstrb(tstrb), .tlast(tlast), .tvalid(tvalid), .tready(tready), .viol(viol));
    axi_viol_log #(.NR(5)) u_log (.clk(aclk), .clear(clear), .en(en), .viol(viol), .now(now), .trig(trig), .any(any),
                                  .rd_sel(rd_sel), .rd_data(rd_data));
endmodule
