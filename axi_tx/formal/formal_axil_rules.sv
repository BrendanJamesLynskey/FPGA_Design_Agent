// formal_axil_rules: SymbiYosys harness of axil_rules (brief 59A). Every bus signal is a free input. The rules are
// restated here as properties, in $past/$stable form and independently of the checker's registered implementation:
//   ref[i] = "rule i is broken in this cycle"
// Tasks (axil_rules.sby, -D defines):
//   QUIET      assume no rule is broken, ever (legal traffic, resets anywhere); assert the checker never fires
//   SEED=k     assume every rule but k holds; assert that whenever rule k is broken the checker's viol[k] is high, and
//              that no other rule fires (cover: rule k broken, the checker firing)
// The outstanding counts of rules 5 and 6 are kept here as their own counters (6 bits: deeper than the BMC depth).
module formal_axil_rules (
    input  logic        clk,
    input  logic        aresetn,
    input  logic [3:0]  awaddr,      // narrow payloads: enough to tell "changed" from "stable"
    input  logic [2:0]  awprot,
    input  logic        awvalid,
    input  logic        awready,
    input  logic [3:0]  wdata,
    input  logic        wstrb,
    input  logic        wvalid,
    input  logic        wready,
    input  logic [1:0]  bresp,
    input  logic        bvalid,
    input  logic        bready,
    input  logic [3:0]  araddr,
    input  logic [2:0]  arprot,
    input  logic        arvalid,
    input  logic        arready,
    input  logic [3:0]  rdata,
    input  logic [1:0]  rresp,
    input  logic        rvalid,
    input  logic        rready
);
    wire [8:0] viol;
    axil_rules #(.ADDR_W(4), .DATA_W(8), .CW(6)) dut (
        .aclk(clk), .aresetn(aresetn), .awaddr(awaddr), .awprot(awprot), .awvalid(awvalid), .awready(awready),
        .wdata({4'b0, wdata}), .wstrb(wstrb), .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid),
        .bready(bready), .araddr(araddr), .arprot(arprot), .arvalid(arvalid), .arready(arready), .rdata({4'b0, rdata}),
        .rresp(rresp), .rvalid(rvalid), .rready(rready), .viol(viol));

    reg f_past_valid = 1'b0;
    always @(posedge clk) f_past_valid <= 1'b1;

    // outstanding (handshaken, not yet answered) AW, W, AR: a response with nothing outstanding consumes nothing
    reg [5:0] oa = 0, ow = 0, orr = 0;
    always @(posedge clk) begin
        if (!aresetn) begin oa <= 0; ow <= 0; orr <= 0; end
        else begin
            oa  <= oa  + (awvalid && awready) - ((bvalid && bready && oa != 0) ? 1 : 0);
            ow  <= ow  + (wvalid && wready)   - ((bvalid && bready && ow != 0) ? 1 : 0);
            orr <= orr + (arvalid && arready) - ((rvalid && rready && orr != 0) ? 1 : 0);
        end
    end

    reg [8:0] ref_;
    reg       was_live;
    always @(posedge clk) begin
        was_live = f_past_valid && $past(aresetn);
        ref_[0] = aresetn && was_live && $past(awvalid && !awready) && !(awvalid && $stable(awaddr) && $stable(awprot));
        ref_[1] = aresetn && was_live && $past(wvalid && !wready) && !(wvalid && $stable(wdata) && $stable(wstrb));
        ref_[2] = aresetn && was_live && $past(bvalid && !bready) && !(bvalid && $stable(bresp));
        ref_[3] = aresetn && was_live && $past(arvalid && !arready) && !(arvalid && $stable(araddr) && $stable(arprot));
        ref_[4] = aresetn && was_live && $past(rvalid && !rready) && !(rvalid && $stable(rdata) && $stable(rresp));
        ref_[5] = aresetn && bvalid && (oa == 0 || ow == 0);
        ref_[6] = aresetn && rvalid && (orr == 0);
        ref_[7] = aresetn && !was_live && (awvalid || wvalid || bvalid || arvalid || rvalid);
        ref_[8] = aresetn && ((bvalid && bresp == 2'b01) || (rvalid && rresp == 2'b01));
`ifdef QUIET
        assume(ref_ == 9'b0);
        assert(viol == 9'b0);
`endif
`ifdef SEED
        assume((ref_ & ~(9'b1 << `SEED)) == 9'b0);
        if (ref_[`SEED]) assert(viol[`SEED]);
        assert((viol & ~(9'b1 << `SEED)) == 9'b0);
        cover(ref_[`SEED] && viol[`SEED]);
`endif
    end
endmodule
