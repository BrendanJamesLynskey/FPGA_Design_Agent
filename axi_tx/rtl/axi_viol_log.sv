// axi_viol_log: counts and time-stamps the violation episodes of a rule monitor (axil_rules, axis_rules). An episode of
// rule i starts in a cycle where viol[i] is high and was low the cycle before (or the log was just cleared), with rule i
// enabled. trig is a one-cycle pulse, registered, one cycle after the first cycle of any episode: the capture trigger.
// Read-out by index (rd_sel, valid the cycle after it changes):
//   0 .. NR-1   episodes of rule i (16-bit, saturating)
//   32          first episode: bit 31 valid, [7:0] rule          33  its time (now at that cycle)
//   34          latest episode: bit 31 valid, [7:0] rule         35  its time
//   36          episodes in total (32-bit, saturating)           37  rules seen (bit i: rule i has fired since clear)
module axi_viol_log #(
    parameter int NR = 9
) (
    input  logic          clk,
    input  logic          clear,
    input  logic [NR-1:0] en,
    input  logic [NR-1:0] viol,
    input  logic [31:0]   now,
    output logic          trig,
    output logic          any,
    input  logic [5:0]    rd_sel,
    output logic [31:0]   rd_data
);
    logic [NR-1:0] p_viol = '0, seen = '0;
    logic [15:0]   cnt [NR];
    logic          first_v = 1'b0, last_v = 1'b0;
    logic [7:0]    first_r = '0, last_r = '0;
    logic [31:0]   first_t = '0, last_t = '0, total = '0;
    wire  [NR-1:0] rise = viol & ~p_viol & en;

    initial begin
        trig = 1'b0;
        for (int i = 0; i < NR; i++) cnt[i] = '0;
    end

    // the lowest-numbered rule of the episodes starting this cycle
    logic [7:0] rise_lo;
    always_comb begin
        rise_lo = '0;
        for (int i = NR - 1; i >= 0; i--) if (rise[i]) rise_lo = 8'(i);
    end

    always_ff @(posedge clk) begin
        trig <= 1'b0;
        if (clear) begin
            p_viol <= '0; seen <= '0; first_v <= 1'b0; last_v <= 1'b0; first_r <= '0; last_r <= '0;
            first_t <= '0; last_t <= '0; total <= '0;
            for (int i = 0; i < NR; i++) cnt[i] <= '0;
        end else begin
            p_viol <= viol;
            if (rise != '0) begin
                trig   <= 1'b1;
                seen   <= seen | rise;
                last_v <= 1'b1; last_r <= rise_lo; last_t <= now;
                if (!first_v) begin first_v <= 1'b1; first_r <= rise_lo; first_t <= now; end
                if (total != 32'hFFFF_FFFF) total <= total + 1'b1;
            end
            for (int i = 0; i < NR; i++) if (rise[i] && cnt[i] != 16'hFFFF) cnt[i] <= cnt[i] + 1'b1;
        end
    end
    assign any = (seen != '0);

    always_ff @(posedge clk) begin
        if (rd_sel < 6'(NR)) rd_data <= {16'b0, cnt[rd_sel[$clog2(NR)-1:0]]};
        else case (rd_sel)
            6'd32: rd_data <= {first_v, 23'b0, first_r};
            6'd33: rd_data <= first_t;
            6'd34: rd_data <= {last_v, 23'b0, last_r};
            6'd35: rd_data <= last_t;
            6'd36: rd_data <= total;
            6'd37: rd_data <= 32'(seen);
            default: rd_data <= '0;
        endcase
    end
endmodule
