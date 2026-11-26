// Muxed-clock domain: 64-bit binary counter, independent Gray twin, checker, saturating error counter,
// gated edge counter, and the two report channels towards clk_c3 (the CDC primitives live in the core).
// The Gray twin is a toggle-rule Gray counter (flip the bit left of the lowest set bit when the parity is
// odd, flip bit 0 when it is even); the checker is pipelined over three register stages.
module mux_domain (
    input  logic        clk,        // clk_mux
    input  logic        rst,        // synchronous to clk (from xpm_cdc_async_rst)
    input  logic        sel_m,      // SEL synchronised into clk
    input  logic        gate_m,     // gate enable synchronised into clk
    output logic        active,     // selection as seen in this domain
    output logic [31:0] ec_data,
    output logic        ec_send,
    input  logic        ec_rcv,
    output logic [63:0] rep_data,   // {errs, counter low 32}
    output logic        rep_send,
    input  logic        rep_rcv
);
    logic [63:0] cnt, prev, gry;
    logic        valid, bad_q, par;
    logic [31:0] errs;
    logic [31:0] ec;
    logic        gate_q, ec_pend;

    // Gray twin next state: toggle mask
    logic [63:0] tog;
    always_comb begin
        tog[0] = ~par;
        for (int i = 1; i < 64; i++) begin
            tog[i] = par && gry[i-1] && (i < 2 ? 1'b1 : ~|(gry & ((64'd1 << (i-1)) - 64'd1)));
        end
        // wrap 1000...0 -> 0 at the top
        tog[63] = par && ((gry[62] && ~|gry[61:0]) || (gry[63] && ~|gry[62:0]));
    end

    // checker pipeline
    logic [63:0] cnt_gray, s1_inc, s1_cnt;
    logic [7:0]  gm;
    logic        v1, g2, c2;
    always_comb begin
        cnt_gray = cnt ^ (cnt >> 1);
        for (int k = 0; k < 8; k++) gm[k] = (gry[8*k +: 8] != cnt_gray[8*k +: 8]);
    end
    logic [7:0] gm_q;

    always_ff @(posedge clk) begin
        if (rst) begin
            cnt <= '0; prev <= '0; gry <= '0; par <= 1'b0; valid <= 1'b0; bad_q <= 1'b0; errs <= '0;
            gm_q <= '0; s1_inc <= '0; s1_cnt <= '0; v1 <= 1'b0; g2 <= 1'b0; c2 <= 1'b0;
            active <= 1'b0; ec <= '0; gate_q <= 1'b0; ec_pend <= 1'b0; ec_send <= 1'b0;
            rep_send <= 1'b0;
        end else begin
            cnt   <= cnt + 64'd1;
            gry   <= gry ^ tog;
            par   <= ~par;
            prev  <= cnt;
            valid <= 1'b1;

            // stage 1
            gm_q   <= gm;
            s1_inc <= prev + 64'd1;
            s1_cnt <= cnt;
            v1     <= valid;
            // stage 2
            g2 <= |gm_q;
            c2 <= v1 && (s1_inc != s1_cnt);
            // stage 3
            bad_q <= g2 || c2;

            if (bad_q && (errs != 32'hFFFFFFFF)) errs <= errs + 32'd1;
            active <= sel_m;

            gate_q <= gate_m;
            if (gate_m) ec <= (gate_q ? ec : 32'd0) + 32'd1;
            if (gate_q && !gate_m) ec_pend <= 1'b1;

            if (ec_send) begin
                if (ec_rcv) ec_send <= 1'b0;
            end else if (ec_pend && !ec_rcv) begin
                ec_data <= ec; ec_send <= 1'b1; ec_pend <= 1'b0;
            end

            if (rep_send) begin
                if (rep_rcv) rep_send <= 1'b0;
            end else if (!rep_rcv) begin
                rep_data <= {errs, cnt[31:0]}; rep_send <= 1'b1;
            end
        end
    end
endmodule
