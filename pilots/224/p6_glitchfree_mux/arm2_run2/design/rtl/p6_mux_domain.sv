// Muxed-domain logic: everything here is clocked by clk_mux only.
// Binary counter + Gray twin with two checkers, saturating error count,
// gate edge counter, and the snapshot / frequency-result handshake sources.
module p6_mux_domain (
    input  logic        clk_mux,
    input  logic        rst_mux,     // active high, synchronous to clk_mux
    input  logic        gate_m,      // gate window, synchronised to clk_mux
    input  logic        snap_tgl_m,  // snapshot request toggle, synchronised to clk_mux
    input  logic        sel_m,       // commanded select, synchronised to clk_mux
    input  logic        s_rcv,       // snapshot return handshake acknowledged
    input  logic        f_rcv,       // frequency return handshake acknowledged
    output logic        act_m,       // select as seen by the running muxed clock
    output logic [31:0] err_cnt,
    output logic        s_send,
    output logic [31:0] s_in,
    output logic        f_send,
    output logic [31:0] f_in
);
    logic [31:0] bin, prev, gray, dec, bin_nx;
    logic        prev_ok, mism, stepbad, gate_q, snap_q, snap_pulse;
    logic [31:0] cnt, s_in_q;
    logic        s_send_q;

    assign bin_nx = bin + 32'd1;

    always_comb begin
        for (int i = 0; i < 32; i++) dec[i] = ^(gray >> i);
    end
    assign mism       = (dec != bin);
    assign stepbad    = prev_ok && (bin != (prev + 32'd1));
    assign snap_pulse = snap_tgl_m ^ snap_q;
    // send starts in the cycle the request is seen (saves a clock); the data is the same value afterwards
    assign s_send = s_send_q | snap_pulse;
    assign s_in   = snap_pulse ? bin : s_in_q;

    always_ff @(posedge clk_mux) begin
        if (rst_mux) begin
            bin <= '0; gray <= '0; prev <= '0; prev_ok <= 1'b0; err_cnt <= '0;
            gate_q <= 1'b0; cnt <= '0; f_in <= '0; s_in_q <= '0;
            s_send_q <= 1'b0; f_send <= 1'b0; act_m <= 1'b0; snap_q <= 1'b0;
        end else begin
            act_m   <= sel_m;
            bin     <= bin_nx;
            gray    <= bin_nx ^ (bin_nx >> 1);
            prev    <= bin;
            prev_ok <= 1'b1;
            if ((mism || stepbad) && (err_cnt != 32'hFFFFFFFF)) err_cnt <= err_cnt + 32'd1;

            gate_q <= gate_m;
            if (gate_m) cnt <= gate_q ? (cnt + 32'd1) : 32'd1;
            if (gate_q && !gate_m) begin f_in <= cnt; f_send <= 1'b1; end
            else if (f_rcv) f_send <= 1'b0;

            snap_q <= snap_tgl_m;
            if (snap_pulse) begin s_in_q <= bin; s_send_q <= 1'b1; end
            else if (s_rcv) s_send_q <= 1'b0;
        end
    end
endmodule
