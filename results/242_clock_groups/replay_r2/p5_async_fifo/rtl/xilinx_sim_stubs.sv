// Simulation-only stand-ins for Xilinx primitives and XPM macros. Vivado supplies the real ones in synthesis.
`ifndef SYNTHESIS

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module BUFG_GT (input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
                input logic [2:0] DIV, input logic I, output logic O);
    assign O = I;
endmodule

module IBUFDS_GTE4 #(parameter logic REFCLK_EN_TX_PATH = 1'b0, parameter logic [1:0] REFCLK_HROW_CK_SEL = 2'b00,
                     parameter logic [1:0] REFCLK_ICNTL_RX = 2'b00)
    (input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2);
    assign O     = I;
    assign ODIV2 = I;
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK    = 1'b0;
    assign DATA      = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1)
    (input logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic              s0 = 1'b0;
    logic [DEST_SYNC_FF-1:0] ch = '0;
    always_ff @(posedge src_clk) s0 <= src_in;
    wire d = (SRC_INPUT_REG != 0) ? s0 : src_in;
    always_ff @(posedge dest_clk) ch <= {ch[DEST_SYNC_FF-2:0], d};
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2)
    (input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s0 = '0;
    logic [WIDTH-1:0] ch [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) ch[i] = '0;
    always_ff @(posedge src_clk) s0 <= src_in;
    wire [WIDTH-1:0] d = (SRC_INPUT_REG != 0) ? s0 : src_in;
    always_ff @(posedge dest_clk) begin
        ch[0] <= d;
        for (int i = 1; i < DEST_SYNC_FF; i++) ch[i] <= ch[i-1];
    end
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

// Simulation model: the reset is applied at the destination clock edge (the real macro asserts asynchronously).
module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0)
    (output logic dest_arst, input logic dest_clk, input logic src_arst);
    wire act = (RST_ACTIVE_HIGH != 0) ? src_arst : ~src_arst;
    logic [DEST_SYNC_FF-1:0] ch = '1;
    always_ff @(posedge dest_clk) begin
        if (act) ch <= '1;
        else     ch <= {ch[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? ch[DEST_SYNC_FF-1] : ~ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_pulse #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
                       parameter int RST_USED = 1, parameter int SIM_ASSERT_CHK = 0)
    (output logic dest_pulse, input logic dest_clk, input logic dest_rst,
     input logic src_clk, input logic src_pulse, input logic src_rst);
    logic tog = 1'b0;
    logic [DEST_SYNC_FF-1:0] ch = '0;
    logic prev = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tog <= ~tog;
    always_ff @(posedge dest_clk) begin
        ch   <= {ch[DEST_SYNC_FF-2:0], tog};
        prev <= ch[DEST_SYNC_FF-1];
    end
    assign dest_pulse = ch[DEST_SYNC_FF-1] ^ prev;
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1)
    (input logic dest_ack, input logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req,
     input logic src_clk, input logic [WIDTH-1:0] src_in, output logic src_rcv, input logic src_send);
    logic [WIDTH-1:0] data = '0;
    logic req_t = 1'b0;
    logic ack_t = 1'b0;
    logic pending = 1'b0;
    logic rcv = 1'b0;
    logic [SRC_SYNC_FF-1:0]  ack_s = '0;
    logic [DEST_SYNC_FF-1:0] req_s = '0;
    always_ff @(posedge src_clk) begin
        ack_s <= {ack_s[SRC_SYNC_FF-2:0], ack_t};
        if (src_send && !rcv && !pending) begin
            data    <= src_in;
            req_t   <= ~req_t;
            pending <= 1'b1;
        end
        if (pending && ack_s[SRC_SYNC_FF-1] == req_t) begin
            pending <= 1'b0;
            rcv     <= 1'b1;
        end
        if (!src_send && !pending) rcv <= 1'b0;
    end
    assign src_rcv = rcv;
    always_ff @(posedge dest_clk) begin
        req_s    <= {req_s[DEST_SYNC_FF-2:0], req_t};
        dest_req <= 1'b0;
        if (req_s[DEST_SYNC_FF-1] != ack_t) begin
            ack_t    <= req_s[DEST_SYNC_FF-1];
            dest_out <= data;
            dest_req <= 1'b1;
        end
    end
    initial begin dest_req = 1'b0; dest_out = '0; end
endmodule

// Behavioural dual-clock FIFO, standard read mode (dout valid the clock after rd_en), capacity FIFO_WRITE_DEPTH.
module xpm_fifo_async #(parameter int CDC_SYNC_STAGES = 2, parameter string DOUT_RESET_VALUE = "0", parameter string ECC_MODE = "no_ecc",
                        parameter string FIFO_MEMORY_TYPE = "auto", parameter int FIFO_READ_LATENCY = 1,
                        parameter int FIFO_WRITE_DEPTH = 2048, parameter int FULL_RESET_VALUE = 0,
                        parameter int PROG_EMPTY_THRESH = 10, parameter int PROG_FULL_THRESH = 10,
                        parameter int RD_DATA_COUNT_WIDTH = 1, parameter int READ_DATA_WIDTH = 32,
                        parameter string READ_MODE = "std", parameter int RELATED_CLOCKS = 0, parameter int SIM_ASSERT_CHK = 0,
                        parameter string USE_ADV_FEATURES = "0707", parameter int WAKEUP_TIME = 0,
                        parameter int WRITE_DATA_WIDTH = 32, parameter int WR_DATA_COUNT_WIDTH = 1)
    (output logic almost_empty, output logic almost_full, output logic data_valid, output logic dbiterr,
     output logic [READ_DATA_WIDTH-1:0] dout, output logic empty, output logic full, output logic overflow,
     output logic prog_empty, output logic prog_full, output logic [RD_DATA_COUNT_WIDTH-1:0] rd_data_count,
     output logic rd_rst_busy, output logic sbiterr, output logic underflow, output logic wr_ack,
     output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count, output logic wr_rst_busy,
     input logic [WRITE_DATA_WIDTH-1:0] din, input logic injectdbiterr, input logic injectsbiterr,
     input logic rd_clk, input logic rd_en, input logic rst, input logic sleep, input logic wr_clk, input logic wr_en);
    localparam int AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wptr = '0;
    logic [AW:0] rptr = '0;
    logic [AW:0] rptr_s1 = '0, rptr_s2 = '0;
    logic [AW:0] wptr_s1 = '0, wptr_s2 = '0;
    logic        rst_r1 = 1'b0, rst_r2 = 1'b0;
    logic [4:0]  wbusy;
    logic [4:0]  rbusy;
    logic        ovf_q = 1'b0, unf_q = 1'b0;

    wire [AW:0] wcount = wptr - rptr_s2;
    assign full          = (wcount == (AW+1)'(FIFO_WRITE_DEPTH));
    assign empty         = (wptr_s2 == rptr);
    assign wr_rst_busy   = rst | (wbusy != 5'd0);
    assign rd_rst_busy   = rst_r2 | (rbusy != 5'd0);
    assign wr_data_count = wcount[WR_DATA_COUNT_WIDTH-1:0];
    assign rd_data_count = (wptr_s2 - rptr);
    assign overflow      = ovf_q;
    assign underflow     = unf_q;
    assign almost_empty  = 1'b0;
    assign almost_full   = 1'b0;
    assign data_valid    = 1'b0;
    assign dbiterr       = 1'b0;
    assign sbiterr       = 1'b0;
    assign prog_empty    = 1'b0;
    assign prog_full     = 1'b0;
    assign wr_ack        = 1'b0;

    always_ff @(posedge wr_clk) begin
        ovf_q   <= wr_en && full;
        rptr_s1 <= rptr;
        rptr_s2 <= rptr_s1;
        if (rst) begin
            wptr    <= '0;
            rptr_s1 <= '0;
            rptr_s2 <= '0;
            wbusy   <= 5'd4;
        end else begin
            if (wbusy != 5'd0) wbusy <= wbusy - 5'd1;
            if (wr_en && !full && wbusy == 5'd0) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
        end
    end

    always_ff @(posedge rd_clk) begin
        unf_q   <= rd_en && empty;
        wptr_s1 <= wptr;
        wptr_s2 <= wptr_s1;
        rst_r1  <= rst;
        rst_r2  <= rst_r1;
        if (rst_r2) begin
            rptr    <= '0;
            wptr_s1 <= '0;
            wptr_s2 <= '0;
            rbusy   <= 5'd16;
        end else begin
            if (rbusy != 5'd0) rbusy <= rbusy - 5'd1;
            if (rd_en && !empty && rbusy == 5'd0) begin
                dout <= mem[rptr[AW-1:0]];
                rptr <= rptr + 1'b1;
            end
        end
    end
    initial dout = '0;
endmodule

`endif
