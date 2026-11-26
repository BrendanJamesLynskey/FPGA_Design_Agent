// Register core: JTAG register port (clk25), FIFOs, run control, CDC and the FIR datapath (clk_dsp).
module fir32_core (
    input  logic        clk25,
    input  logic        clk_dsp,
    input  logic        rst,            // active high, clk25 domain
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,            // led[0] BUSY; led[1] is driven by the top (MMCM locked)
    output logic        sfp_tx_disable
);
    localparam logic [31:0] DESIGN_ID = 32'h20940001;
    localparam logic [11:0] A_ID = 12'h000, A_BUILD = 12'h004, A_SCR = 12'h008, A_CTRL = 12'h010,
                            A_PUSH = 12'h014, A_POP = 12'h018, A_STAT = 12'h01C, A_SAT = 12'h020,
                            A_DONE = 12'h024;

    assign sfp_tx_disable = 1'b1;

    /* verilator lint_off UNUSEDSIGNAL */
    // ------------------------------------------------------------------ reset into clk_dsp
    logic rst_dsp;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_dsp (
        .dest_clk(clk_dsp), .src_arst(rst), .dest_arst(rst_dsp));

    // ------------------------------------------------------------------ build stamp
    logic [31:0] build_raw, build_q;
    logic        build_dv, build_cfgclk;
    USR_ACCESSE2 u_usr (.DATA(build_raw), .DATAVALID(build_dv), .CFGCLK(build_cfgclk));
    // the configuration-clock domain word is quasi-static: cross it through a named synchroniser
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(32)) u_build_sync (
        .src_clk(1'b0), .src_in(build_raw), .dest_clk(clk25), .dest_out(build_q));

    // ------------------------------------------------------------------ clk25 state
    logic [31:0] scratch;
    logic        busy25;
    logic [3:0]  clr_hold;
    logic [2:0]  in_rst_cnt;
    logic        clear_pulse, run_pulse;
    logic [10:0] n_run;
    logic [31:0] sat25, done25;
    logic [15:0] pk [4];
    logic [2:0]  pk_n;

    wire         in_rst = rst | (in_rst_cnt != 3'd0);
    wire  [10:0] in_wr_cnt;
    wire         in_wr_busy, in_full;
    wire  [15:0] in_dout;
    wire         in_empty, in_rd_busy;
    wire  [10:0] in_rd_cnt;
    wire         in_rd_en;

    wire  [11:0] in_cnt  = 12'(in_wr_cnt) + 12'(pk_n);
    wire         push_req = h_we && (h_addr == A_PUSH);
    wire         push_ok  = push_req && (in_cnt < 12'd1024);
    wire         in_ready = !in_wr_busy && !in_rst;
    wire         pk_wr    = in_ready && (pk_n != 3'd0);
    wire         dir_wr   = in_ready && (pk_n == 3'd0) && push_ok;
    wire         app      = push_ok && !dir_wr && (pk_n != 3'd4 || pk_wr);
    wire  [2:0]  app_idx  = pk_n - 3'(pk_wr);
    wire         in_wr_en = pk_wr | dir_wr;
    wire  [15:0] in_din   = pk_wr ? pk[0] : h_wdata[15:0];

    xpm_fifo_async #(.CDC_SYNC_STAGES(2), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"), .FIFO_READ_LATENCY(0),
        .FIFO_WRITE_DEPTH(1024), .READ_DATA_WIDTH(16), .READ_MODE("fwft"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0),
        .USE_ADV_FEATURES("0404"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16), .RD_DATA_COUNT_WIDTH(11),
        .WR_DATA_COUNT_WIDTH(11)) u_in_fifo (
        .sleep(1'b0), .rst(in_rst),
        .wr_clk(clk25), .wr_en(in_wr_en), .din(in_din), .full(in_full), .wr_rst_busy(in_wr_busy),
        .wr_data_count(in_wr_cnt),
        .rd_clk(clk_dsp), .rd_en(in_rd_en), .dout(in_dout), .empty(in_empty), .rd_rst_busy(in_rd_busy),
        .rd_data_count(in_rd_cnt), .injectsbiterr(1'b0), .injectdbiterr(1'b0));

    // ------------------------------------------------------------------ output FIFO (write side clk_dsp)
    logic        out_rst;
    wire         out_wr_en;
    wire  [15:0] out_din;
    wire         out_full, out_wr_busy, out_rd_busy, out_empty;
    wire  [10:0] out_wr_cnt, out_rd_cnt;
    wire  [15:0] out_dout;
    wire         out_rd_en = h_re && (h_addr == A_POP) && !out_empty && (clr_hold == 4'd0) && !out_rd_busy;

    xpm_fifo_async #(.CDC_SYNC_STAGES(2), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"), .FIFO_READ_LATENCY(0),
        .FIFO_WRITE_DEPTH(1024), .READ_DATA_WIDTH(16), .READ_MODE("fwft"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0),
        .USE_ADV_FEATURES("0404"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(16), .RD_DATA_COUNT_WIDTH(11),
        .WR_DATA_COUNT_WIDTH(11)) u_out_fifo (
        .sleep(1'b0), .rst(out_rst),
        .wr_clk(clk_dsp), .wr_en(out_wr_en), .din(out_din), .full(out_full), .wr_rst_busy(out_wr_busy),
        .wr_data_count(out_wr_cnt),
        .rd_clk(clk25), .rd_en(out_rd_en), .dout(out_dout), .empty(out_empty), .rd_rst_busy(out_rd_busy),
        .rd_data_count(out_rd_cnt), .injectsbiterr(1'b0), .injectdbiterr(1'b0));

    // ------------------------------------------------------------------ crossings clk25 <-> clk_dsp
    wire         clr_p, run_p;
    wire  [10:0] n_s;
    wire         dsp_busy, dsp_busy_s;
    wire         hs_rcv, dl_req;
    wire  [63:0] dl_out;
    logic        hs_send;
    logic [63:0] hs_in;

    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_clr_cdc (
        .src_clk(clk25), .src_rst(1'b0), .src_pulse(clear_pulse), .dest_clk(clk_dsp), .dest_rst(1'b0),
        .dest_pulse(clr_p));
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_run_cdc (
        .src_clk(clk25), .src_rst(1'b0), .src_pulse(run_pulse), .dest_clk(clk_dsp), .dest_rst(1'b0),
        .dest_pulse(run_p));
    xpm_cdc_array_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(11)) u_n_cdc (
        .src_clk(clk25), .src_in(n_run), .dest_clk(clk_dsp), .dest_out(n_s));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_busy_cdc (
        .src_clk(clk_dsp), .src_in(dsp_busy), .dest_clk(clk25), .dest_out(dsp_busy_s));
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(4),
        .WIDTH(64)) u_cnt_cdc (
        .src_clk(clk_dsp), .src_in(hs_in), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk25), .dest_ack(1'b0), .dest_req(dl_req), .dest_out(dl_out));

    // ------------------------------------------------------------------ clk25 register logic
    logic dbq, armed;
    always_ff @(posedge clk25) begin
        clear_pulse <= 1'b0;
        run_pulse   <= 1'b0;
        dbq         <= dsp_busy_s;
        // push buffer (holds pushes while the input FIFO is in reset)
        if (pk_wr) begin
            pk[0] <= pk[1]; pk[1] <= pk[2]; pk[2] <= pk[3];
        end
        if (app) pk[app_idx[1:0]] <= h_wdata[15:0];
        pk_n <= pk_n - 3'(pk_wr) + 3'(app);
        if (in_rst_cnt != 3'd0) in_rst_cnt <= in_rst_cnt - 3'd1;
        if (clr_hold != 4'd0)   clr_hold   <= clr_hold - 4'd1;
        if (busy25 && dsp_busy_s && !dbq) armed <= 1'b1;
        if (armed && !dsp_busy_s) begin armed <= 1'b0; busy25 <= 1'b0; end
        if (dl_req && busy25) begin
            sat25 <= dl_out[63:32]; done25 <= dl_out[31:0]; busy25 <= 1'b0;
        end
        if (!busy25) armed <= 1'b0;
        if (h_we && h_addr == A_SCR) scratch <= h_wdata;
        if (h_we && h_addr == A_CTRL) begin
            if (h_wdata[0]) begin
                clear_pulse <= 1'b1; in_rst_cnt <= 3'd4; clr_hold <= 4'd8;
                busy25 <= 1'b0; armed <= 1'b0; sat25 <= '0; done25 <= '0; pk_n <= 3'd0;
            end else if (h_wdata[1] && !busy25 && in_cnt != 12'd0) begin
                run_pulse <= 1'b1; n_run <= in_cnt[10:0]; busy25 <= 1'b1;
            end
        end
        if (rst) begin
            scratch <= '0; busy25 <= 1'b0; armed <= 1'b0; clr_hold <= '0; in_rst_cnt <= '0;
            clear_pulse <= 1'b0; run_pulse <= 1'b0; n_run <= '0; sat25 <= '0; done25 <= '0; pk_n <= '0;
        end
    end

    wire [31:0] status = {1'b0, out_rd_cnt & {11{clr_hold == 4'd0}}, 4'd0, in_cnt, 3'd0, busy25};
    always_ff @(posedge clk25) begin
        if (h_re) begin
            case (h_addr)
                A_ID:    h_rdata <= DESIGN_ID;
                A_BUILD: h_rdata <= build_q;
                A_SCR:   h_rdata <= scratch;
                A_POP:   h_rdata <= (!out_empty && clr_hold == 4'd0 && !out_rd_busy) ? {1'b1, 15'd0, out_dout} : 32'd0;
                A_STAT:  h_rdata <= status;
                A_SAT:   h_rdata <= sat25;
                A_DONE:  h_rdata <= done25;
                default: h_rdata <= 32'd0;
            endcase
        end
        if (rst) h_rdata <= '0;
    end

    assign led = {1'b1, busy25};

    // ------------------------------------------------------------------ clk_dsp control
    typedef enum logic [2:0] {S_IDLE, S_RUN, S_DRAIN, S_SEND, S_WAIT} st_t;
    st_t         st;
    logic        run_pend;
    logic [1:0]  run_dly;
    logic [10:0] n_lat, rem;
    logic [4:0]  out_rst_cnt;
    logic [7:0]  sh8;
    logic [31:0] sat_cnt, done_cnt;
    wire         fir_clr;
    wire         fir_valid, fir_sat;
    wire  [15:0] fir_y;
    logic        clr_q;

    wire  [3:0]  infl = 4'(sh8[0]) + 4'(sh8[1]) + 4'(sh8[2]) + 4'(sh8[3]) + 4'(sh8[4]) + 4'(sh8[5]) + 4'(sh8[6])
                      + 4'(sh8[7]);
    wire         room    = ({1'b0, out_wr_cnt} + 12'(infl)) < 12'd1024;
    wire         issue   = (st == S_RUN) && !in_empty && !in_rd_busy && !out_wr_busy && room;
    assign       in_rd_en = issue;
    assign       out_wr_en  = fir_valid && !out_wr_busy;
    assign       out_din    = fir_y;
    assign       dsp_busy   = (st != S_IDLE) || run_pend;
    assign       fir_clr    = clr_q | rst_dsp;
    always_comb  out_rst    = rst_dsp | (out_rst_cnt != 5'd0);

    always_ff @(posedge clk_dsp) begin
        clr_q   <= clr_p;
        run_dly <= {run_dly[0], run_p};
        sh8     <= {sh8[6:0], issue};
        if (out_rst_cnt != 5'd0) out_rst_cnt <= out_rst_cnt - 5'd1;
        if (run_dly[1]) begin run_pend <= 1'b1; n_lat <= n_s; end
        if (fir_valid) begin
            done_cnt <= done_cnt + 32'd1;
            sat_cnt  <= sat_cnt + 32'(fir_sat);
        end
        case (st)
            S_IDLE: if (run_pend && out_rst_cnt == 5'd0 && !out_wr_busy && !in_rd_busy) begin
                        run_pend <= 1'b0; rem <= n_lat; st <= (n_lat == 11'd0) ? S_DRAIN : S_RUN;
                    end
            S_RUN: if (issue) begin
                        rem <= rem - 11'd1;
                        if (rem == 11'd1) st <= S_DRAIN;
                    end
            S_DRAIN: if (sh8 == 8'd0 && !issue) begin
                        hs_in <= {sat_cnt, done_cnt}; hs_send <= 1'b1; st <= S_SEND;
                    end
            S_SEND: if (hs_rcv) begin hs_send <= 1'b0; st <= S_WAIT; end
            S_WAIT: if (!hs_rcv) st <= S_IDLE;
            default: st <= S_IDLE;
        endcase
        if (clr_p) begin
            st <= S_IDLE; run_pend <= 1'b0; run_dly <= 2'd0; hs_send <= 1'b0;
            sat_cnt <= '0; done_cnt <= '0; out_rst_cnt <= 5'd16;
        end
        if (rst_dsp) begin
            st <= S_IDLE; run_pend <= 1'b0; run_dly <= 2'd0; hs_send <= 1'b0; sh8 <= '0;
            sat_cnt <= '0; done_cnt <= '0; out_rst_cnt <= 5'd0; clr_q <= 1'b0;
        end
    end

    fir_dsp u_fir (
        .clk(clk_dsp), .clr(fir_clr), .in_valid(issue), .in_x(in_dout),
        .out_valid(fir_valid), .out_y(fir_y), .out_sat(fir_sat));
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
