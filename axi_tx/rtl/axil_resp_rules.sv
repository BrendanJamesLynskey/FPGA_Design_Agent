// axil_resp_rules: the missing-response rule of the AXI4-Lite protocol monitor (brief 71), a passive monitor of one
// interface's handshakes, placed beside axil_rules (axil_checker). Port-only. Rule, in our own words (Arm IHI 0022H A3.3:
// every accepted write gets one write response and every accepted read one read response):
//   10 RESP_LOST  while a write is outstanding (an AW and a W handshake both done and not yet answered by a B), a B
//                 handshake comes within TIMEOUT clocks of the later of that moment and the previous B; the same for
//                 reads (AR handshakes and R). lost[0] (writes) or lost[1] (reads) is high in every cycle past the bound.
// A response with nothing outstanding is rules 5 and 6 of axil_rules. The bound is a parameter: a slave that is legally
// slower than TIMEOUT clocks fires the rule, so TIMEOUT is set from the slave's documented worst case. Brief 69 found the
// case it exists for: the AXI DMA register port accepted a second write while the first B waited, and returned one B.
// Outstanding counts saturate at 2**CW - 1, as in axil_rules. Not evaluated while ARESETn is low.
module axil_resp_rules #(
    parameter int TIMEOUT = 256,
    parameter int CW      = 8
) (
    input  logic       aclk,
    input  logic       aresetn,
    input  logic       awvalid,
    input  logic       awready,
    input  logic       wvalid,
    input  logic       wready,
    input  logic       bvalid,
    input  logic       bready,
    input  logic       arvalid,
    input  logic       arready,
    input  logic       rvalid,
    input  logic       rready,
    output logic [1:0] lost
);
    localparam int AW = $clog2(TIMEOUT + 2);
    localparam logic [CW-1:0] MAXC = {CW{1'b1}};
    localparam logic [AW-1:0] MAXA = {AW{1'b1}};
    logic [CW-1:0] aw_pend = '0, w_pend = '0, ar_pend = '0;
    logic [AW-1:0] wage = '0, rage = '0;
    wire awhs = awvalid && awready, whs = wvalid && wready, bhs = bvalid && bready;
    wire arhs = arvalid && arready, rhs = rvalid && rready;
    wire wpend = (aw_pend != '0) && (w_pend != '0);
    wire rpend = (ar_pend != '0);

    function automatic logic [CW-1:0] upd(input logic [CW-1:0] c, input logic inc, input logic dec);
        if (inc && !dec)      upd = (c == MAXC) ? c : c + 1'b1;
        else if (dec && !inc) upd = (c == '0) ? c : c - 1'b1;
        else                  upd = c;
    endfunction

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            aw_pend <= '0; w_pend <= '0; ar_pend <= '0; wage <= '0; rage <= '0;
        end else begin
            aw_pend <= upd(aw_pend, awhs, bhs);
            w_pend  <= upd(w_pend,  whs,  bhs);
            ar_pend <= upd(ar_pend, arhs, rhs);
            wage <= (bhs || !wpend) ? '0 : ((wage == MAXA) ? wage : wage + 1'b1);
            rage <= (rhs || !rpend) ? '0 : ((rage == MAXA) ? rage : rage + 1'b1);
        end
    end
    assign lost[0] = aresetn && wpend && (wage >= AW'(TIMEOUT));
    assign lost[1] = aresetn && rpend && (rage >= AW'(TIMEOUT));
endmodule
