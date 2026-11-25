// feed_arb_in.sv: one feed's input stage of feed_arb (brief 191): a word FIFO, the header capture of the packet's first three words, the per-packet verdict flags, and the drain of dropped packets.
// See feed_arb.sv for the rules and the latency; this module only stores, reports the header and forwards or drops as told.
module feed_arb_in #(
    parameter int AW = 5                 // FIFO depth: 2^AW words
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          v, sof, eof, err,
    input  logic [63:0]   d,
    input  logic [7:0]    keep,
    // header of the packet whose third word is being written (valid with h3)
    output logic          h3,
    output logic [79:0]   h_sess,
    output logic [63:0]   h_seq,
    output logic [15:0]   h_neff,
    output logic          h_hb,
    output logic [15:0]   h_rawc,        // the count field (0 heartbeat, 0xFFFF end of session)
    input  logic          h3_fwd,        // the decision on that header (comb, same clock)
    output logic          fb_fwd,        // a packet ended with no header decision (runt, or words lost): forwarded unchanged
    output logic          ovf_p,         // a word or a packet was dropped on overflow (one clock each)
    // read side
    output logic          fwd_ready,     // the head of the FIFO is the first word of a forwarded packet
    output logic          occ_nz,
    output logic [74:0]   head,
    input  logic          pop            // pop the head (a forwarded packet's word)
);
    localparam int DEPTH = 1 << AW;
    logic [74:0]    mem [DEPTH];
    logic [DEPTH-1:0] vdv, vdf;
    logic [AW:0]    wp, rp, occ;
    logic [AW-1:0]  wix, rix, first;
    logic [1:0]     wi;
    logic [63:0]    hw0, hw1;
    logic           pk_ovf, skip, decided, pm_drop;
    logic [3:0]     nv;
    logic [1:0]     widx;
    logic           room, wr;
    always_comb begin
        wix = wp[AW-1:0]; rix = rp[AW-1:0]; occ = wp - rp;
        nv = 4'd8;
        if (eof) begin
            case (keep)
                8'h01: nv = 4'd1; 8'h03: nv = 4'd2; 8'h07: nv = 4'd3; 8'h0F: nv = 4'd4;
                8'h1F: nv = 4'd5; 8'h3F: nv = 4'd6; 8'h7F: nv = 4'd7; default: nv = 4'd8;
            endcase
        end
        widx = sof ? 2'd0 : wi;
        // the first and the last word of a packet may take any free slot; the others leave one free for the last word
        room = (eof || sof) ? (occ != DEPTH[AW:0]) : (occ < DEPTH[AW:0] - 1'b1);
        wr   = v && room && !(skip && !sof);
        h3   = wr && (widx == 2'd2) && (nv >= 4'd4) && !pk_ovf && !skip && !sof;
        h_sess = {hw1[15:0], hw0};
        h_seq  = {hw1[23:16], hw1[31:24], hw1[39:32], hw1[47:40], hw1[55:48], hw1[63:56], d[7:0], d[15:8]};
        h_rawc = {d[23:16], d[31:24]};
        h_hb   = ({d[23:16], d[31:24]} == 16'd0) || ({d[23:16], d[31:24]} == 16'hFFFF);
        h_neff = h_hb ? 16'd0 : {d[23:16], d[31:24]};
        fb_fwd = wr && eof && (sof || !decided) && !h3;
        ovf_p  = v && (!wr && !(skip && !sof));
        head   = mem[rix];
        occ_nz = (occ != '0);
        fwd_ready = occ_nz && head[73] && vdv[rix] && vdf[rix] && !pm_drop;
    end

    logic drain;
    assign drain = occ_nz && !pm_drop && head[73] && vdv[rix] && !vdf[rix] || (occ_nz && pm_drop);
    always_ff @(posedge clk) begin
        if (rst) begin
            wp <= '0; rp <= '0; wi <= '0; hw0 <= '0; hw1 <= '0; pk_ovf <= 1'b0; skip <= 1'b0; decided <= 1'b0; pm_drop <= 1'b0; vdv <= '0; vdf <= '0; first <= '0;
        end else begin
            if (v) begin
                if (sof) begin
                    pk_ovf <= 1'b0; decided <= 1'b0;
                    skip <= !room;                                  // no slot even for the first word: the whole packet is dropped
                end
                if (wr) begin
                    mem[wix] <= {err | (pk_ovf & !sof), sof, eof, keep, d};
                    wp <= wp + 1'b1;
                    if (sof) begin first <= wix; vdv[wix] <= 1'b0; vdf[wix] <= 1'b0; hw0 <= d; end
                    if (widx == 2'd1) hw1 <= d;
                    wi <= eof ? 2'd0 : ((widx == 2'd3) ? 2'd3 : widx + 2'd1);
                end else begin
                    if (!(skip && !sof)) pk_ovf <= 1'b1;
                    wi <= eof ? 2'd0 : wi;
                end
                if (eof) skip <= 1'b0;
            end
            if (h3) begin
                decided <= 1'b1;
                vdv[first] <= 1'b1; vdf[first] <= h3_fwd;
            end
            if (fb_fwd) begin
                decided <= 1'b1;
                vdv[sof ? wix : first] <= 1'b1; vdf[sof ? wix : first] <= 1'b1;
            end
            if (pop || drain) begin
                rp <= rp + 1'b1;
                if (drain) pm_drop <= !head[72];
            end
        end
    end
endmodule
