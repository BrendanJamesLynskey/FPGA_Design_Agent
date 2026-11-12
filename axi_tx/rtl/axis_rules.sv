// axis_rules: AXI4-Stream rules as a passive monitor of one stream's ports (brief 59A). viol[i] is high in every cycle in
// which rule i is broken. Rules 0-2 are the protocol's; 3 and 4 are profile rules (off unless enabled in the log), for IP
// that documents a maximum packet length or packed bytes. Cited to Arm IHI 0051B (AXI4-Stream) by section, our words:
//   0 HOLD      once TVALID is high it stays high, with TDATA, TKEEP, TSTRB and TLAST unchanged, until TREADY  (2.2)
//   1 KEEP_STRB a byte with TKEEP low and TSTRB high is the reserved combination and must not appear           (2.4, Table 2-3)
//   2 RESET     TVALID is low at the first edge at which reset is seen released                                (2.8)
//   3 MAXLEN    profile: no packet longer than maxlen beats (maxlen 0: off)
//   4 PACKED    profile: TKEEP all ones on every beat but the last; on the last, a non-zero run of ones from byte 0
module axis_rules #(
    parameter int DATA_W = 32,
    parameter int LEN_W  = 16
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic [LEN_W-1:0]    maxlen,
    input  logic [DATA_W-1:0]   tdata,
    input  logic [DATA_W/8-1:0] tkeep,
    input  logic [DATA_W/8-1:0] tstrb,
    input  logic                tlast,
    input  logic                tvalid,
    input  logic                tready,
    output logic [4:0]          viol
);
    localparam int KW = DATA_W / 8;
    logic              p_rstn = 1'b0, p_v = 1'b0, p_r = 1'b0, p_last = 1'b0;
    logic [DATA_W-1:0] p_data = '0;
    logic [KW-1:0]     p_keep = '0, p_strb = '0;
    logic [LEN_W-1:0]  beats = '0;                  // beats of the current packet already transferred
    wire               hs = tvalid && tready;

    always_ff @(posedge aclk) begin
        p_rstn <= aresetn; p_v <= tvalid; p_r <= tready; p_data <= tdata; p_keep <= tkeep; p_strb <= tstrb; p_last <= tlast;
        if (!aresetn)          beats <= '0;
        else if (hs && tlast)  beats <= '0;
        else if (hs && beats != {LEN_W{1'b1}}) beats <= beats + 1'b1;
    end

    wire live = aresetn && p_rstn;
    wire [KW-1:0] keep_p1 = tkeep + 1'b1;
    wire packed_last = (tkeep != '0) && ((tkeep & keep_p1) == '0);
    always_comb begin
        viol    = '0;
        viol[0] = live && p_v && !p_r && (!tvalid || tdata != p_data || tkeep != p_keep || tstrb != p_strb || tlast != p_last);
        viol[1] = aresetn && tvalid && ((~tkeep & tstrb) != '0);
        viol[2] = aresetn && !p_rstn && tvalid;
        viol[3] = aresetn && hs && (maxlen != '0) && ({1'b0, beats} + 1'b1 > {1'b0, maxlen});
        viol[4] = aresetn && tvalid && (tlast ? !packed_last : (tkeep != {KW{1'b1}}));
    end
endmodule
