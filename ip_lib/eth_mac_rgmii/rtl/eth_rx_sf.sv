// eth_rx_sf.sv: store-and-forward receive buffer behind mac_rx (eth_mac_rgmii with CUT_THROUGH = 0).
//
// The frame's bytes are written as they arrive; at its end a good frame is committed without its FCS and a bad one
// is rolled back (dropped and counted). Committed frames leave on an AXI-Stream master with tready back-pressure,
// tlast on the last byte. A frame that does not fit in the free space is dropped whole (ev_overflow); at most
// NFRAMES frames wait at once. One clock domain.
//
// end_keep = 0 rolls back a good frame without counting it as dropped or overflowed: the address filter's and the MAC
// control frames' verdict (the caller counts those). STRIP = 1 removes an 802.1Q or 802.1ad tag (TPID 0x8100 or
// 0x88A8 at bytes 12-13) from the stored frame; its TCI (bytes 14-15) leaves on m_axis_tci with m_axis_tagged = 1,
// beside every byte of that frame. RAM selects the buffer's memory: "bram" (block RAM) or "lutram" (LUT RAM); the
// function is the same.

module eth_rx_sf #(
    parameter int DEPTH   = 4096,       // bytes, a power of two
    parameter int NFRAMES = 16,         // frames waiting, a power of two
    parameter int LEN_W   = 11,         // width of end_len (14 for jumbo frames)
    parameter int STRIP   = 0,          // 1: strip one VLAN tag
    parameter     RAM     = "bram"      // "bram" or "lutram"
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    input  logic             in_sof,
    input  logic [7:0]       in_data,
    input  logic             end_valid,
    input  logic             end_good,
    input  logic             end_keep,  // 0: roll back this good frame silently (filtered, or a MAC control frame)
    input  logic [LEN_W-1:0] end_len,   // FCS included
    output logic [7:0]       m_axis_tdata,
    output logic             m_axis_tvalid,
    input  logic             m_axis_tready,
    output logic             m_axis_tlast,
    output logic [15:0]      m_axis_tci,
    output logic             m_axis_tagged,
    output logic             ev_dropped,     // a bad frame was dropped
    output logic             ev_overflow     // a frame was dropped for want of room
);
    localparam int AW = $clog2(DEPTH);
    localparam int FW = $clog2(NFRAMES);
    initial begin
        if ((1 << AW) != DEPTH || DEPTH < 2048 || DEPTH > 65536) $error("eth_rx_sf: DEPTH must be a power of two in 2048..65536 (got %0d)", DEPTH);
        if ((1 << FW) != NFRAMES || NFRAMES < 2 || NFRAMES > 256) $error("eth_rx_sf: NFRAMES must be a power of two in 2..256 (got %0d)", NFRAMES);
        if (STRIP != 0 && STRIP != 1) $error("eth_rx_sf: STRIP must be 0 or 1 (got %0d)", STRIP);
        if (RAM != "bram" && RAM != "lutram") $error("eth_rx_sf: RAM must be \"bram\" or \"lutram\"");
    end
    logic [AW:0]  wp, cw, rp;           // write, committed write, read (one extra bit: full/empty)
    logic         full_frame;           // this frame ran out of room
    logic [LEN_W-1:0] lens [NFRAMES];
    logic [16:0]  tcis [NFRAMES];       // {vtag, TCI}
    logic [FW:0]  lw, lr;
    logic [AW:0]  used;
    assign used = wp - rp;

    // VLAN tag removal: the byte index within the frame, the tag seen at bytes 12-13, its TCI
    logic [LEN_W-1:0] bi;
    logic [7:0]   b12;
    logic         vtag, w12;
    logic [15:0]  tci;
    logic         tpid, skip;
    assign tpid = (STRIP != 0) && in_valid && !in_sof && bi == LEN_W'(13) &&
                  ({b12, in_data} == 16'h8100 || {b12, in_data} == 16'h88A8);
    assign skip = tpid || (vtag && (bi == LEN_W'(14) || bi == LEN_W'(15)));
    logic [LEN_W-1:0] keep_len;         // stored length: the frame without its FCS (and tag)
    assign keep_len = end_len - LEN_W'(vtag ? 8 : 4);

    logic we;
    assign we = in_valid && !skip && used != (AW+1)'(DEPTH);
    always_ff @(posedge clk) begin
        ev_dropped <= 1'b0; ev_overflow <= 1'b0;
        if (rst) begin wp <= '0; cw <= '0; lw <= '0; full_frame <= 1'b0; bi <= '0; vtag <= 1'b0; w12 <= 1'b0;
                       b12 <= '0; tci <= '0; end
        else begin
            if (in_valid) begin
                if (in_sof) bi <= LEN_W'(1);
                else if (bi != '1) bi <= bi + 1'b1;
                if (in_sof) begin full_frame <= 1'b0; vtag <= 1'b0; end
                if (!in_sof && bi == LEN_W'(12)) begin b12 <= in_data; w12 <= (used != (AW+1)'(DEPTH)); end
                if (tpid) vtag <= 1'b1;
                if (vtag && bi == LEN_W'(14)) tci[15:8] <= in_data;
                if (vtag && bi == LEN_W'(15)) tci[7:0]  <= in_data;
                if (tpid) begin
                    if (w12) wp <= wp - 1'b1;                   // give back the tag's first byte
                    else full_frame <= 1'b1;
                end else if (!skip) begin
                    if (used == (AW+1)'(DEPTH)) full_frame <= 1'b1;
                    else wp <= wp + 1'b1;
                end
            end
            if (end_valid) begin
                if (end_good && end_keep && !full_frame && (lw - lr) != (FW+1)'(NFRAMES) && end_len > LEN_W'(vtag ? 8 : 4)) begin
                    lens[lw[FW-1:0]] <= keep_len;
                    tcis[lw[FW-1:0]] <= {vtag, tci};
                    lw <= lw + 1'b1;
                    cw <= cw + (AW+1)'(keep_len);
                    wp <= cw + (AW+1)'(keep_len);              // the FCS bytes are given back
                end else begin
                    wp <= cw;
                    if (end_good && end_keep) ev_overflow <= 1'b1;
                    else if (!end_good) ev_dropped <= 1'b1;
                end
                vtag <= 1'b0;
            end
        end
    end

    // read side: a frame is sent when its length is known (committed); a two-entry output stage keeps the RAM's
    // read latency off the tready path
    logic [LEN_W-1:0] left;
    logic        busy;
    logic        rv;                    // RAM output valid
    logic [7:0]  rq;
    logic        rlast;
    logic [16:0] cur_t, rq_t;
    logic        take;
    assign take = !m_axis_tvalid || m_axis_tready;
    logic rd_en;
    assign rd_en = busy && (take || !rv);
    if (RAM == "lutram") begin : g_lutram
        (* ram_style = "distributed" *) logic [7:0] mem [DEPTH];
        always_ff @(posedge clk) begin
            if (we) mem[wp[AW-1:0]] <= in_data;
            if (rd_en) rq <= mem[rp[AW-1:0]];
        end
    end else begin : g_bram
        (* ram_style = "block" *) logic [7:0] mem [DEPTH];
        always_ff @(posedge clk) begin                  // plain RAM ports, for block RAM
            if (we) mem[wp[AW-1:0]] <= in_data;
            if (rd_en) rq <= mem[rp[AW-1:0]];
        end
    end
    always_ff @(posedge clk) begin
        if (rst) begin rp <= '0; lr <= '0; left <= '0; busy <= 1'b0; rv <= 1'b0; m_axis_tvalid <= 1'b0; m_axis_tlast <= 1'b0;
                   m_axis_tdata <= '0; rlast <= 1'b0; cur_t <= '0; rq_t <= '0; m_axis_tci <= '0; m_axis_tagged <= 1'b0; end
        else begin
            if (take) begin
                m_axis_tvalid <= rv;
                m_axis_tdata  <= rq;
                m_axis_tlast  <= rlast;
                m_axis_tci    <= rq_t[15:0];
                m_axis_tagged <= rq_t[16];
                rv <= 1'b0;
            end
            if (!busy && lw != lr && !rv) begin
                busy <= 1'b1; left <= lens[lr[FW-1:0]]; cur_t <= tcis[lr[FW-1:0]]; lr <= lr + 1'b1;
            end else if (rd_en) begin
                rv <= 1'b1;
                rlast <= (left == LEN_W'(1));
                rq_t <= cur_t;
                rp <= rp + 1'b1;
                left <= left - 1'b1;
                if (left == LEN_W'(1)) busy <= 1'b0;
            end
        end
    end
endmodule
