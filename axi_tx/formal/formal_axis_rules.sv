// formal_axis_rules: SymbiYosys harness of axis_rules (brief 59A), the same pattern as formal_axil_rules: free stream
// inputs (and a free maxlen), the rules restated as properties, tasks QUIET and SEED=k.
module formal_axis_rules (
    input  logic        clk,
    input  logic        aresetn,
    input  logic [2:0]  maxlen,
    input  logic [3:0]  tdata,
    input  logic [1:0]  tkeep,
    input  logic [1:0]  tstrb,
    input  logic        tlast,
    input  logic        tvalid,
    input  logic        tready
);
    wire [4:0] viol;
    // 16-bit data, two bytes: TKEEP and TSTRB are 2 bits
    axis_rules #(.DATA_W(16), .LEN_W(3)) dut (
        .aclk(clk), .aresetn(aresetn), .maxlen(maxlen), .tdata({12'b0, tdata}), .tkeep(tkeep), .tstrb(tstrb),
        .tlast(tlast), .tvalid(tvalid), .tready(tready), .viol(viol));

    reg f_past_valid = 1'b0;
    always @(posedge clk) f_past_valid <= 1'b1;
    // beats of the current packet already transferred (saturating at 7: the checker's LEN_W)
    reg [2:0] nb = 0;
    always @(posedge clk)
        if (!aresetn) nb <= 0;
        else if (tvalid && tready) nb <= tlast ? 3'd0 : (nb == 3'd7 ? nb : nb + 3'd1);

    reg [4:0] ref_;
    reg       was_live;
    always @(posedge clk) begin
        was_live = f_past_valid && $past(aresetn);
        ref_[0] = aresetn && was_live && $past(tvalid && !tready) &&
                  !(tvalid && $stable(tdata) && $stable(tkeep) && $stable(tstrb) && $stable(tlast));
        ref_[1] = aresetn && tvalid && ((tkeep[0] == 1'b0 && tstrb[0]) || (tkeep[1] == 1'b0 && tstrb[1]));
        ref_[2] = aresetn && !was_live && tvalid;
        ref_[3] = aresetn && tvalid && tready && maxlen != 0 && ({1'b0, nb} >= {1'b0, maxlen});
        ref_[4] = aresetn && tvalid && (tlast ? !(tkeep == 2'b01 || tkeep == 2'b11) : tkeep != 2'b11);
`ifdef QUIET
        assume(ref_ == 5'b0);
        assert(viol == 5'b0);
`endif
`ifdef SEED
        assume((ref_ & ~(5'b1 << `SEED)) == 5'b0);
        if (ref_[`SEED]) assert(viol[`SEED]);
        assert((viol & ~(5'b1 << `SEED)) == 5'b0);
        cover(ref_[`SEED] && viol[`SEED]);
`endif
    end
endmodule
