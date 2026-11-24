// mdio_master.sv: IEEE 802.3 clause 22 management interface (MDC/MDIO) master, one read or write at a time.
//
// Frame: 32 preamble ones, start 01, opcode (10 read, 01 write), PHY address, register address, turnaround (read:
// released, write: 10), 16 data bits, most significant first. Each bit lasts 2*DIV clocks: MDC low for the first
// half (MDIO changes at its start), high for the second; read bits are sampled at the rising edge of MDC. At 125 MHz,
// DIV = 32 gives MDC = 1.95 MHz, under the 2.5 MHz of clause 22.
// mdio_t = 1 releases the line (the pin's pull-up holds it high). The line changes DIV clocks after each rising edge
// of MDC, the last release included, so the hold time after the PHY's sampling edge is DIV clock periods (clause 22
// asks for 10 ns).
// Library entry (brief 63D), first written for designs/b58a_trigger; that design keeps its own copy.

module mdio_master #(
    parameter int DIV = 32
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic        rd,             // 1 read, 0 write
    input  logic [4:0]  phy,
    input  logic [4:0]  reg_a,
    input  logic [15:0] wdata,
    output logic [15:0] rdata,
    output logic        busy,
    output logic        mdc,
    output logic        mdio_o,
    output logic        mdio_t,
    input  logic        mdio_i
);
    initial begin
        if (DIV < 2 || DIV > 1024) $error("mdio_master: DIV must be in 2..1024 (got %0d)", DIV);
    end
    logic [63:0] sh;                    // bits still to send, first in [63]
    logic [63:0] oe;                    // 1 = drive this bit
    logic [6:0]  nb;                    // bits left
    logic [10:0] t;
    logic        r;

    always_ff @(posedge clk) begin
        if (rst) begin
            sh <= '0; oe <= '0; nb <= '0; t <= '0; r <= 1'b0; busy <= 1'b0; rdata <= '0;
            mdc <= 1'b0; mdio_o <= 1'b1; mdio_t <= 1'b1;
        end else if (!busy) begin
            mdc <= 1'b0; mdio_t <= 1'b1; mdio_o <= 1'b1;
            if (go) begin
                busy <= 1'b1; r <= rd; nb <= 7'd64; t <= '0;
                sh <= {32'hFFFF_FFFF, 2'b01, rd ? 2'b10 : 2'b01, phy, reg_a, rd ? 2'b11 : 2'b10, rd ? 16'h0 : wdata};
                oe <= {32'hFFFF_FFFF, 2'b11, 2'b11, 5'h1F, 5'h1F, rd ? 2'b00 : 2'b11, rd ? 16'h0 : 16'hFFFF};
            end
        end else begin
            if (t == 11'd0) begin                                   // bit start: MDC low, present the bit
                mdc <= 1'b0;
                mdio_o <= sh[63];
                mdio_t <= !oe[63];
            end
            if (t == 11'(DIV)) begin                                // rising edge of MDC: the PHY samples, we sample
                mdc <= 1'b1;
                if (r && nb <= 7'd16) rdata <= {rdata[14:0], mdio_i};
            end
            if (t == 11'(2 * DIV - 1)) begin
                t <= '0;
                sh <= {sh[62:0], 1'b0};
                oe <= {oe[62:0], 1'b0};
                nb <= nb - 7'd1;
                if (nb == 7'd1) begin busy <= 1'b0; mdc <= 1'b0; end      // the line is released one clock later
            end else t <= t + 11'd1;
        end
    end

`ifdef FORMAL
    // Properties for SymbiYosys (formal/mdio.sby; proved by k-induction there). The frame position is bit 64 - nb,
    // clock t of it; the line changes only on t = 0 (visible from t = 1).
    logic f_init = 1'b1;
    logic f_busy_q = 1'b0;
    always_ff @(posedge clk) begin f_init <= rst; f_busy_q <= busy; end
    // Every assertion is labelled (a_*) and paired with a cover of its own antecedent (a_*__ante; brief 143c, flow/formal_rigour.py).
    always_ff @(posedge clk) if (!f_init && !rst) begin
        if (busy) begin
            a_counters_in_range: assert (t <= 11'(2 * DIV - 1) && nb >= 7'd1 && nb <= 7'd64);
            a_output_enable_mask: assert (oe == ((r ? {46'h3FFF_FFFF_FFFF, 18'h0} : 64'hFFFF_FFFF_FFFF_FFFF) << (7'd64 - nb)));
            // MDC low for the first DIV clocks of a bit time, high for the rest
            a_mdc_phase: assert (mdc == (t > 11'(DIV) || (t == 11'd0 && nb != 7'd64)));
            // what is on the line is the current bit (from t = 1)
            if (t != 11'd0) a_line_is_current_bit: assert (mdio_t == !oe[63] && (mdio_t || mdio_o == sh[63]));
            // a read releases the line from the turnaround on; a write drives it throughout
            if (t != 11'd0 && r && nb <= 7'd18) a_read_releases_line: assert (mdio_t);
            if (t != 11'd0 && !r) a_write_drives_line: assert (!mdio_t);
        end else begin
            a_idle_mdc_low: assert (!mdc);
            if (!f_busy_q) a_idle_line_released: assert (mdio_t && mdio_o);
        end
        // setup and hold: the line is steady at a rising edge of MDC and one clock after it
        if ($rose(mdc)) a_setup_at_rise: assert ($stable(mdio_o) && $stable(mdio_t));
        if (busy && mdc && $past(mdc) && t == 11'(DIV + 2) % 11'(2 * DIV)) a_hold_after_rise: assert ($stable(mdio_o) && $stable(mdio_t));
    end
    // antecedents (same guard): the condition each assertion sits under
    always_ff @(posedge clk) if (!f_init && !rst) begin
        a_busy__ante: cover (busy && nb == 7'd1);                       // a_counters_in_range, a_output_enable_mask, a_mdc_phase: the last bit of a frame is reached
        a_line_is_current_bit__ante: cover (busy && t != 11'd0);
        a_read_releases_line__ante: cover (busy && t != 11'd0 && r && nb <= 7'd18);
        a_write_drives_line__ante: cover (busy && t != 11'd0 && !r);
        a_idle_mdc_low__ante: cover (!busy);
        a_idle_line_released__ante: cover (!busy && !f_busy_q);
        a_setup_at_rise__ante: cover ($rose(mdc));
        a_hold_after_rise__ante: cover (busy && mdc && $past(mdc) && t == 11'(DIV + 2) % 11'(2 * DIV));
        c_read_frame_done: cover (f_busy_q && !busy && r);
        c_write_frame_done: cover (f_busy_q && !busy && !r);
    end
`endif
endmodule
