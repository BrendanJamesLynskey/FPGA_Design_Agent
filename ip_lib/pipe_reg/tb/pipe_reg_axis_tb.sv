// pipe_reg_axis_tb.sv: the simulation top of the Icarus benches: pipe_reg plus the AXI4-Stream rule monitor
// (axi_tx/rtl/axis_rules.sv) on its slave and master ports. viol_s / viol_m are high in every clock a rule is broken
// (bit 0 hold, 1 tkeep/tstrb, 2 reset); they are 0 when W is not a multiple of 8 (the monitor needs byte lanes).
module pipe_reg_axis_tb #(
    parameter int W        = 32,
    parameter int N        = 1,
    parameter int MODE     = 1,
    parameter int TLAST_EN = 0,
    parameter int TKEEP_EN = 0,
    parameter int TUSER_W  = 0
) (
    input  logic                         aclk,
    input  logic                         aresetn,
    input  logic                         s_axis_tvalid,
    output logic                         s_axis_tready,
    input  logic [W-1:0]                 s_axis_tdata,
    input  logic                         s_axis_tlast,
    input  logic [(W/8 > 0 ? W/8 : 1)-1:0] s_axis_tkeep,
    input  logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] s_axis_tuser,
    output logic                         m_axis_tvalid,
    input  logic                         m_axis_tready,
    output logic [W-1:0]                 m_axis_tdata,
    output logic                         m_axis_tlast,
    output logic [(W/8 > 0 ? W/8 : 1)-1:0] m_axis_tkeep,
    output logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] m_axis_tuser,
    output logic [4:0]                   viol_s,
    output logic [4:0]                   viol_m
);
    pipe_reg #(.W(W), .N(N), .MODE(MODE), .TLAST_EN(TLAST_EN), .TKEEP_EN(TKEEP_EN), .TUSER_W(TUSER_W)) dut (.*);
    generate
        if (W % 8 == 0 && W >= 8) begin : g_mon
            localparam int KW = W / 8;
            wire [KW-1:0] ones = '1;
            wire [KW-1:0] sk = (TKEEP_EN != 0) ? s_axis_tkeep : ones;
            wire [KW-1:0] mk = (TKEEP_EN != 0) ? m_axis_tkeep : ones;
            axis_rules #(.DATA_W(W)) mon_s (.aclk, .aresetn, .maxlen('0), .tdata(s_axis_tdata), .tkeep(sk), .tstrb(sk),
                                            .tlast(s_axis_tlast), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .viol(viol_s));
            axis_rules #(.DATA_W(W)) mon_m (.aclk, .aresetn, .maxlen('0), .tdata(m_axis_tdata), .tkeep(mk), .tstrb(mk),
                                            .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol_m));
        end else begin : g_nomon
            assign viol_s = '0;
            assign viol_m = '0;
        end
    endgenerate
endmodule
