// Simulation-only stand-ins for Xilinx primitives and XPM macros (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS

// The source register of the real macro (SRC_INPUT_REG) is not modelled: the stand-in is a pure synchroniser.
module xpm_cdc_single #(
    parameter int DEST_SYNC_FF   = 4,
    parameter int INIT_SYNC_FF   = 0,
    parameter int SIM_ASSERT_CHK = 0,
    parameter int SRC_INPUT_REG  = 1
) (
    input  logic src_clk,
    input  logic src_in,
    input  logic dest_clk,
    output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] sync = '0;
    always_ff @(posedge dest_clk) sync <= {sync[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sync[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF   = 4,
    parameter int INIT_SYNC_FF   = 0,
    parameter int SIM_ASSERT_CHK = 0,
    parameter int SRC_INPUT_REG  = 1,
    parameter int WIDTH          = 2
) (
    input  logic             src_clk,
    input  logic [WIDTH-1:0] src_in,
    input  logic             dest_clk,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] sync [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sync[i] = '0;
    always_ff @(posedge dest_clk) begin
        sync[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sync[i] <= sync[i-1];
    end
    assign dest_out = sync[DEST_SYNC_FF-1];
endmodule

// Four-phase handshake model (DEST_EXT_HSK = 0 only; dest_ack ignored).
module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK   = 1,
    parameter int DEST_SYNC_FF   = 4,
    parameter int INIT_SYNC_FF   = 0,
    parameter int SIM_ASSERT_CHK = 0,
    parameter int SRC_SYNC_FF    = 4,
    parameter int WIDTH          = 1
) (
    input  logic             src_clk,
    input  logic [WIDTH-1:0] src_in,
    input  logic             src_send,
    output logic             src_rcv,
    input  logic             dest_clk,
    output logic [WIDTH-1:0] dest_out,
    output logic             dest_req,
    input  logic             dest_ack
);
    logic [WIDTH-1:0]        data  = '0;
    logic                    req   = 1'b0;
    logic                    busy  = 1'b0;
    logic                    rcv_q = 1'b0;
    logic [SRC_SYNC_FF-1:0]  ack_sync = '0;
    logic [DEST_SYNC_FF-1:0] req_sync = '0;
    logic                    req_d = 1'b0;
    logic                    ack   = 1'b0;
    logic                    ack_s;
    logic                    req_s;
    assign ack_s = ack_sync[SRC_SYNC_FF-1];
    assign req_s = req_sync[DEST_SYNC_FF-1];

    always_ff @(posedge src_clk) begin
        ack_sync <= {ack_sync[SRC_SYNC_FF-2:0], ack};
        if (!busy) begin
            if (src_send && !rcv_q) begin
                data <= src_in;
                req  <= 1'b1;
                busy <= 1'b1;
            end else if (!src_send) begin
                rcv_q <= 1'b0;
            end
        end else begin
            if (ack_s && req) begin
                req   <= 1'b0;
                rcv_q <= 1'b1;
            end else if (!req && !ack_s) begin
                busy <= 1'b0;
            end
        end
    end

    always_ff @(posedge dest_clk) begin
        req_sync <= {req_sync[DEST_SYNC_FF-2:0], req};
        req_d    <= req_s;
        ack      <= req_s;
    end

    assign src_rcv  = rcv_q;
    assign dest_req = req_s & ~req_d;
    assign dest_out = data;
endmodule

// Behavioural asynchronous FIFO (Gray pointers, two-flop synchronisers, first-word-fall-through).
module xpm_fifo_async #(
    parameter int    CDC_SYNC_STAGES     = 2,
    parameter string DOUT_RESET_VALUE    = "0",
    parameter string ECC_MODE            = "no_ecc",
    parameter string FIFO_MEMORY_TYPE    = "auto",
    parameter int    FIFO_READ_LATENCY   = 1,
    parameter int    FIFO_WRITE_DEPTH    = 2048,
    parameter int    FULL_RESET_VALUE    = 0,
    parameter int    READ_DATA_WIDTH     = 32,
    parameter string READ_MODE           = "std",
    parameter int    RELATED_CLOCKS      = 0,
    parameter int    SIM_ASSERT_CHK      = 0,
    parameter string USE_ADV_FEATURES    = "0707",
    parameter int    WAKEUP_TIME         = 0,
    parameter int    WRITE_DATA_WIDTH    = 32,
    parameter int    WR_DATA_COUNT_WIDTH = 12
) (
    input  logic                           sleep,
    input  logic                           rst,
    input  logic                           wr_clk,
    input  logic                           wr_en,
    input  logic [WRITE_DATA_WIDTH-1:0]    din,
    output logic                           full,
    output logic                           wr_rst_busy,
    output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    input  logic                           rd_clk,
    input  logic                           rd_en,
    output logic [READ_DATA_WIDTH-1:0]     dout,
    output logic                           empty,
    output logic                           rd_rst_busy,
    input  logic                           injectsbiterr,
    input  logic                           injectdbiterr
);
    localparam int AW = $clog2(FIFO_WRITE_DEPTH);

    function automatic logic [AW:0] g2b(input logic [AW:0] g);
        logic [AW:0] b;
        b[AW] = g[AW];
        for (int i = AW - 1; i >= 0; i--) b[i] = b[i+1] ^ g[i];
        return b;
    endfunction

    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wbin = '0;
    logic [AW:0] rbin = '0;
    logic [AW:0] wg1 = '0, wg2 = '0;     // write Gray pointer in the read domain
    logic [AW:0] rg1 = '0, rg2 = '0;     // read Gray pointer in the write domain
    logic [AW:0] wgray, rgray;
    logic [2:0]  wcnt = '0, rcnt = '0;
    logic        rr1 = 1'b0, rr2 = 1'b0;
    logic [AW:0] rbin_w, wbin_r;
    logic        wbusy, rbusy;

    assign wgray  = wbin ^ (wbin >> 1);
    assign rgray  = rbin ^ (rbin >> 1);
    assign rbin_w = g2b(rg2);
    assign wbin_r = g2b(wg2);
    assign wbusy  = rst | (wcnt != 3'd0);
    assign rbusy  = rr2 | (rcnt != 3'd0);

    always_ff @(posedge wr_clk) begin
        if (rst) begin
            wbin <= '0;
            rg1  <= '0;
            rg2  <= '0;
            wcnt <= 3'd4;
        end else begin
            rg1 <= rgray;
            rg2 <= rg1;
            if (wcnt != 3'd0) wcnt <= wcnt - 3'd1;
            if (wr_en && !full && !wbusy) begin
                mem[wbin[AW-1:0]] <= din;
                wbin <= wbin + 1'b1;
            end
        end
    end

    always_ff @(posedge rd_clk) begin
        rr1 <= rst;
        rr2 <= rr1;
        if (rr2) begin
            rbin <= '0;
            wg1  <= '0;
            wg2  <= '0;
            rcnt <= 3'd4;
        end else begin
            wg1 <= wgray;
            wg2 <= wg1;
            if (rcnt != 3'd0) rcnt <= rcnt - 3'd1;
            if (rd_en && !empty && !rbusy) rbin <= rbin + 1'b1;
        end
    end

    assign full          = ((wbin - rbin_w) == (AW+1)'(FIFO_WRITE_DEPTH));
    assign wr_data_count = wbin - rbin_w;
    assign empty         = (wbin_r == rbin);
    assign dout          = mem[rbin[AW-1:0]];
    assign wr_rst_busy   = wbusy;
    assign rd_rst_busy   = rbusy;
endmodule

module USR_ACCESSE2 (
    output logic        CFGCLK,
    output logic [31:0] DATA,
    output logic        DATAVALID
);
    assign CFGCLK    = 1'b0;
    assign DATA      = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module IBUFDS_GTE4 #(
    parameter logic       REFCLK_EN_TX_PATH = 1'b0,
    parameter logic [1:0] REFCLK_HROW_CK_SEL = 2'b00,
    parameter logic [1:0] REFCLK_ICNTL_RX = 2'b00
) (
    output logic O,
    output logic ODIV2,
    input  logic CEB,
    input  logic I,
    input  logic IB
);
    assign O     = CEB ? 1'b0 : (I & ~IB);
    assign ODIV2 = O;
endmodule

module BUFG_GT (
    output logic       O,
    input  logic       CE,
    input  logic       CEMASK,
    input  logic       CLR,
    input  logic       CLRMASK,
    input  logic [2:0] DIV,
    input  logic       I
);
    assign O = (CE && !CLR) ? I : 1'b0;
endmodule

`endif
