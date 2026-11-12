// mac_tx.sv: Ethernet transmit MAC, one byte per enabled clock, to a GMII-style byte interface.
//
// A frame starts when start is high while ready (idle, inter-frame gap served): seven preamble bytes 0x55, the SFD
// 0xD5, the data bytes up to the one marked last (zero-padded to MIN_DATA), the FCS (inverted CRC-32, least
// significant byte first), then at least IFG_BYTES idle byte times. The MAC moves one byte on each clock with ce high
// (every clock at 1000 Mb/s; one in 10 or 100 at 100 or 10 Mb/s, set by rgmii_tx).
//
// Data provider: req_idx names the byte the MAC needs at its next byte time (req_valid high); the provider answers on
// in_data/in_last by then (one clock later at the latest, so it can register its multiplexer). in_last marks the
// frame's last data byte; after it the MAC stops asking.
//
// Output timing: txd/tx_en are registers; first_pulse, sof_pulse and last_pulse are aligned with txd (the first
// preamble byte, the SFD, the last FCS byte): the "first bit out" and timestamp points.
//
// poison: high on any clock up to the one that forms the last FCS byte makes the remaining FCS bytes go out
// inverted, so the far end discards the frame (the trading path's speculative undo, and an AXI-Stream underrun in
// eth_mac_rgmii). last_poisoned (with last_pulse) says whether any FCS byte was inverted.

module mac_tx #(
    parameter int MIN_DATA  = 60,       // pad to this many data bytes (FCS excluded)
    parameter int IFG_BYTES = 12        // idle byte times after the FCS
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        ce,             // byte enable (1 at 1000 Mb/s)
    input  logic        start,
    output logic        ready,
    output logic [10:0] req_idx,
    output logic        req_valid,
    input  logic [7:0]  in_data,
    input  logic        in_last,
    input  logic        poison,
    output logic [7:0]  txd,
    output logic        tx_en,
    output logic        first_pulse,
    output logic        sof_pulse,
    output logic        last_pulse,
    output logic        last_poisoned,
    output logic        busy
);
    initial begin
        if (MIN_DATA < 1 || MIN_DATA > 1514) $error("mac_tx: MIN_DATA must be in 1..1514 (got %0d)", MIN_DATA);
        if (IFG_BYTES < 1 || IFG_BYTES > 255) $error("mac_tx: IFG_BYTES must be in 1..255 (got %0d)", IFG_BYTES);
    end

    localparam logic [2:0] S_IDLE = 3'd0, S_PRE = 3'd1, S_SFD = 3'd2, S_DATA = 3'd3, S_FCS = 3'd4, S_IFG = 3'd5;
    logic [2:0]  st;
    logic [10:0] i;
    logic [7:0]  cnt;
    logic        pz, ended;
    logic [31:0] crc_q;
    logic [7:0]  dbyte, obyte;
    logic        oen, pz_now, cur_last, data_done;

    assign dbyte     = ended ? 8'h00 : in_data;
    assign cur_last  = !ended && in_last;
    assign data_done = (ended || cur_last) && (i + 11'd1 >= 11'(MIN_DATA));
    assign pz_now    = pz | poison;
    eth_crc32 u_crc (.clk(clk), .rst(rst), .init(st != S_DATA && st != S_FCS), .en(st == S_DATA && ce), .d(dbyte),
                     .crc(crc_q), .residue_ok());
    assign ready = (st == S_IDLE);
    assign busy  = (st != S_IDLE);

    always_comb begin
        req_valid = 1'b0;
        req_idx   = '0;
        if (st == S_SFD)                             begin req_valid = 1'b1; req_idx = 11'd0; end
        else if (st == S_DATA && !ended && !in_last) begin req_valid = 1'b1; req_idx = i + 11'd1; end
    end

    logic [31:0] fcs;
    assign fcs = ~crc_q;
    always_comb begin
        oen = 1'b1;
        case (st)
            S_PRE:  obyte = 8'h55;
            S_SFD:  obyte = 8'hD5;
            S_DATA: obyte = dbyte;
            S_FCS: begin
                case (cnt[1:0])
                    2'd0:    obyte = fcs[7:0];
                    2'd1:    obyte = fcs[15:8];
                    2'd2:    obyte = fcs[23:16];
                    default: obyte = fcs[31:24];
                endcase
                if (pz_now) obyte = ~obyte;
            end
            default: begin obyte = 8'h00; oen = 1'b0; end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; i <= '0; cnt <= '0; pz <= 1'b0; ended <= 1'b0;
            txd <= '0; tx_en <= 1'b0; first_pulse <= 1'b0; sof_pulse <= 1'b0; last_pulse <= 1'b0; last_poisoned <= 1'b0;
        end else begin
            first_pulse <= 1'b0; sof_pulse <= 1'b0; last_pulse <= 1'b0;
            if (st != S_IDLE && st != S_IFG && poison) pz <= 1'b1;
            if (ce) begin
                txd         <= obyte;
                tx_en       <= oen;
                first_pulse <= (st == S_PRE) && (cnt == 8'd0);
                sof_pulse   <= (st == S_SFD);
                last_pulse  <= (st == S_FCS) && (cnt == 8'd3);
                if (st == S_FCS && cnt == 8'd3) last_poisoned <= pz_now;
                case (st)
                    S_IDLE: if (start) begin st <= S_PRE; cnt <= 8'd0; pz <= poison; end
                    S_PRE: begin
                        cnt <= cnt + 8'd1;
                        if (cnt == 8'd6) st <= S_SFD;
                    end
                    S_SFD: begin st <= S_DATA; i <= '0; ended <= 1'b0; end
                    S_DATA: begin
                        i <= i + 11'd1;
                        if (cur_last) ended <= 1'b1;
                        if (data_done) begin st <= S_FCS; cnt <= 8'd0; end
                    end
                    S_FCS: begin
                        cnt <= cnt + 8'd1;
                        if (cnt == 8'd3) begin st <= S_IFG; cnt <= 8'd0; end
                    end
                    default: begin                              // S_IFG
                        cnt <= cnt + 8'd1;
                        if (cnt + 8'd1 >= 8'(IFG_BYTES)) st <= S_IDLE;
                    end
                endcase
            end
        end
    end
endmodule
