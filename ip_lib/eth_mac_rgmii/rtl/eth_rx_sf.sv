// eth_rx_sf.sv: store-and-forward receive buffer behind mac_rx (eth_mac_rgmii with CUT_THROUGH = 0).
//
// The frame's bytes are written as they arrive; at its end a good frame is committed without its FCS and a bad one
// is rolled back (dropped and counted). Committed frames leave on an AXI-Stream master with tready back-pressure,
// tlast on the last byte. A frame that does not fit in the free space is dropped whole (ev_overflow); at most
// NFRAMES frames wait at once. One clock domain.

module eth_rx_sf #(
    parameter int DEPTH   = 4096,       // bytes, a power of two
    parameter int NFRAMES = 16          // frames waiting, a power of two
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic        in_sof,
    input  logic [7:0]  in_data,
    input  logic        end_valid,
    input  logic        end_good,
    input  logic [10:0] end_len,        // FCS included
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        ev_dropped,     // a bad frame was dropped
    output logic        ev_overflow     // a frame was dropped for want of room
);
    localparam int AW = $clog2(DEPTH);
    localparam int FW = $clog2(NFRAMES);
    initial begin
        if ((1 << AW) != DEPTH || DEPTH < 2048 || DEPTH > 65536) $error("eth_rx_sf: DEPTH must be a power of two in 2048..65536 (got %0d)", DEPTH);
        if ((1 << FW) != NFRAMES || NFRAMES < 2 || NFRAMES > 256) $error("eth_rx_sf: NFRAMES must be a power of two in 2..256 (got %0d)", NFRAMES);
    end
    (* ram_style = "block" *) logic [7:0] mem [DEPTH];
    logic [AW:0]  wp, cw, rp;           // write, committed write, read (one extra bit: full/empty)
    logic         full_frame;           // this frame ran out of room
    logic [10:0]  lens [NFRAMES];
    logic [FW:0]  lw, lr;
    logic [AW:0]  used;
    assign used = wp - rp;

    always_ff @(posedge clk) begin
        ev_dropped <= 1'b0; ev_overflow <= 1'b0;
        if (rst) begin wp <= '0; cw <= '0; lw <= '0; full_frame <= 1'b0; end
        else begin
            if (in_valid) begin
                if (in_sof) full_frame <= 1'b0;
                if (used == (AW+1)'(DEPTH)) full_frame <= 1'b1;
                else wp <= wp + 1'b1;
            end
            if (end_valid) begin
                if (end_good && !full_frame && (lw - lr) != (FW+1)'(NFRAMES) && end_len > 11'd4) begin
                    lens[lw[FW-1:0]] <= end_len - 11'd4;
                    lw <= lw + 1'b1;
                    cw <= cw + (AW+1)'(end_len - 11'd4);
                    wp <= cw + (AW+1)'(end_len - 11'd4);       // the FCS bytes are given back
                end else begin
                    wp <= cw;
                    if (end_good) ev_overflow <= 1'b1; else ev_dropped <= 1'b1;
                end
            end
        end
    end

    // read side: a frame is sent when its length is known (committed); a two-entry output stage keeps the RAM's
    // read latency off the tready path
    logic [10:0] left;
    logic        busy;
    logic        rv;                    // RAM output valid
    logic [7:0]  rq;
    logic        rlast;
    logic        take;
    assign take = !m_axis_tvalid || m_axis_tready;
    logic rd_en, we;
    assign rd_en = busy && (take || !rv);
    assign we    = in_valid && used != (AW+1)'(DEPTH);
    always_ff @(posedge clk) begin                      // plain RAM ports, for block RAM
        if (we) mem[wp[AW-1:0]] <= in_data;
        if (rd_en) rq <= mem[rp[AW-1:0]];
    end
    always_ff @(posedge clk) begin
        if (rst) begin rp <= '0; lr <= '0; left <= '0; busy <= 1'b0; rv <= 1'b0; m_axis_tvalid <= 1'b0; m_axis_tlast <= 1'b0;
                   m_axis_tdata <= '0; rlast <= 1'b0; end
        else begin
            if (take) begin
                m_axis_tvalid <= rv;
                m_axis_tdata  <= rq;
                m_axis_tlast  <= rlast;
                rv <= 1'b0;
            end
            if (!busy && lw != lr && !rv) begin
                busy <= 1'b1; left <= lens[lr[FW-1:0]]; lr <= lr + 1'b1;
            end else if (rd_en) begin
                rv <= 1'b1;
                rlast <= (left == 11'd1);
                rp <= rp + 1'b1;
                left <= left - 11'd1;
                if (left == 11'd1) busy <= 1'b0;
            end
        end
    end
endmodule
