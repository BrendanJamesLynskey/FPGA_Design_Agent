// Register core of the 32-tap symmetric FIR: register map, sample memories, run control, LEDs.
// clk_25 domain: register port, memories' host sides, counters. clk_dp domain: datapath.
// Crossings: command and done messages by xpm_cdc_handshake; sample memories are dual-clock
// block RAM whose contents are only read after the handshake that announces them.
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off UNUSEDSIGNAL */
module fir32_core #(
    parameter logic [31:0] DESIGN_ID = 32'h20940001
) (
    input  logic        clk_25,
    input  logic        clk_dp,
    input  logic        rst,            // active high, clk_25 domain
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    input  logic [31:0] build_word,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // clk_dp side signals
    logic [9:0]  in_addr, out_wp;
    logic [10:0] iss_left, res_left, sat_acc;
    logic        rv, pend_done, pend_ack, dclr, v_out, res_we, sat_out;
    logic [15:0] y_out;

    // ------------------------------------------------------------------ clk_dp reset
    logic rst_dp;
    reset_sync u_rsync (.dest_clk(clk_dp), .src_rst(rst), .dest_rst(rst_dp));

    // ------------------------------------------------------------------ clk_25 side
    logic [9:0]  in_wp, in_rp, out_rp;
    logic [10:0] in_cnt, out_cnt, run_n, fin_sat;
    logic [31:0] scratch, sat_cnt, done_cnt, cmd_r;
    logic [30:0] run_cmd_r;
    logic        busy, sticky, pend_run, pend_clear, sending, fin_pend;
    logic [1:0]  clrs_out;
    logic [2:0]  fin_t;
    logic        src_rcv, msg_req;
    logic [15:0] msg_d;
    logic [15:0] in_dout, out_dout;

    logic        clr_w, run_w, run_go, push_ok, pop_ok, fin_apply, clr_wait, clr_send, ack_rx, done_rx;
    logic [10:0] space, n_calc;
    logic [1:0]  clrs_nxt;

    assign clr_w     = h_we && (h_addr == 12'h010) && h_wdata[0];
    assign run_w     = h_we && (h_addr == 12'h010) && !h_wdata[0] && h_wdata[1] && !busy;
    assign space     = 11'd1024 - out_cnt;
    assign n_calc    = (in_cnt < space) ? in_cnt : space;
    assign run_go    = run_w && (n_calc != 11'd0);
    assign push_ok   = h_we && (h_addr == 12'h014) && (in_cnt < 11'd1024);
    assign pop_ok    = h_re && (h_addr == 12'h018) && (out_cnt != 11'd0);
    assign fin_apply = fin_pend && (fin_t == 3'd3);
    assign clr_wait  = pend_clear || (clrs_out != 2'd0);
    assign clr_send  = !sending && !src_rcv && pend_clear;
    assign ack_rx    = msg_req && msg_d[15];
    assign done_rx   = msg_req && !msg_d[15] && !clr_wait && busy && !fin_pend;
    assign clrs_nxt  = clrs_out + {1'b0, clr_send} - {1'b0, ack_rx};

    always_ff @(posedge clk_25) begin
        if (rst) begin
            scratch <= '0; in_wp <= '0; in_rp <= '0; out_rp <= '0; in_cnt <= '0; out_cnt <= '0;
            run_n <= '0; busy <= 1'b0; sticky <= 1'b0; pend_run <= 1'b0; pend_clear <= 1'b0;
            sending <= 1'b0; fin_pend <= 1'b0; fin_t <= '0; clrs_out <= '0; sat_cnt <= '0; done_cnt <= '0;
            h_rdata <= '0;
        end else begin
            // ---- command sender (handshake to clk_dp)
            clrs_out <= clrs_nxt;
            if (!sending) begin
                if (!src_rcv) begin
                    if (pend_clear) begin
                        cmd_r <= 32'h8000_0000; sending <= 1'b1; pend_clear <= 1'b0;
                    end else if (pend_run && clrs_out == 2'd0) begin
                        cmd_r <= {1'b0, run_cmd_r}; sending <= 1'b1; pend_run <= 1'b0;
                    end
                end
            end else if (src_rcv) begin
                sending <= 1'b0;
            end

            // ---- done message from clk_dp, applied after a settling delay
            if (done_rx) begin
                fin_pend <= 1'b1; fin_t <= '0; fin_sat <= msg_d[10:0];
            end
            if (fin_pend) begin
                fin_t <= fin_t + 3'd1;
                if (fin_apply) begin
                    fin_pend <= 1'b0; busy <= 1'b0;
                    sat_cnt  <= sat_cnt + 32'(fin_sat);
                    done_cnt <= done_cnt + 32'(run_n);
                    if (fin_sat != 11'd0) sticky <= 1'b1;
                end
            end

            // ---- sample counts
            in_cnt  <= in_cnt + 11'(push_ok) - (fin_apply ? run_n : 11'd0);
            out_cnt <= out_cnt + (fin_apply ? run_n : 11'd0) - 11'(pop_ok);
            if (push_ok) in_wp <= in_wp + 10'd1;
            if (pop_ok)  out_rp <= out_rp + 10'd1;

            // ---- host writes
            if (h_we && h_addr == 12'h008) scratch <= h_wdata;
            if (run_go) begin
                busy <= 1'b1; run_n <= n_calc; pend_run <= 1'b1;
                run_cmd_r <= {in_rp, (out_rp + out_cnt[9:0]), n_calc};
                in_rp <= in_rp + n_calc[9:0];
            end
            if (clr_w) begin
                in_wp <= '0; in_rp <= '0; out_rp <= '0; in_cnt <= '0; out_cnt <= '0; run_n <= '0;
                busy <= 1'b0; sticky <= 1'b0; pend_run <= 1'b0; pend_clear <= 1'b1;
                fin_pend <= 1'b0; sat_cnt <= '0; done_cnt <= '0;
            end

            // ---- read port
            if (h_re) begin
                case (h_addr)
                    12'h000: h_rdata <= DESIGN_ID;
                    12'h004: h_rdata <= build_word;
                    12'h008: h_rdata <= scratch;
                    12'h018: h_rdata <= (out_cnt != 11'd0) ? {1'b1, 15'd0, out_dout} : 32'd0;
                    12'h01C: h_rdata <= {1'b0, out_cnt, 4'd0, 1'b0, in_cnt, 3'd0, busy};
                    12'h020: h_rdata <= sat_cnt;
                    12'h024: h_rdata <= done_cnt;
                    default: h_rdata <= 32'd0;
                endcase
            end
        end
    end

    assign led = {sticky, busy};

    // ------------------------------------------------------------------ memories
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(10), .ADDR_WIDTH_B(10), .BYTE_WRITE_WIDTH_A(16), .CLOCKING_MODE("independent_clock"),
        .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE(16384), .READ_DATA_WIDTH_B(16), .READ_LATENCY_B(1),
        .WRITE_DATA_WIDTH_A(16)
    ) u_in_mem (
        .sleep(1'b0), .clka(clk_25), .ena(push_ok), .wea(push_ok), .addra(in_wp), .dina(h_wdata[15:0]),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .clkb(clk_dp), .enb(1'b1), .addrb(in_addr), .doutb(in_dout), .regceb(1'b1), .rstb(1'b0),
        .sbiterrb(), .dbiterrb()
    );

    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(10), .ADDR_WIDTH_B(10), .BYTE_WRITE_WIDTH_A(16), .CLOCKING_MODE("independent_clock"),
        .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE(16384), .READ_DATA_WIDTH_B(16), .READ_LATENCY_B(1),
        .WRITE_DATA_WIDTH_A(16)
    ) u_out_mem (
        .sleep(1'b0), .clka(clk_dp), .ena(res_we), .wea(res_we), .addra(out_wp), .dina(y_out),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .clkb(clk_25), .enb(1'b1), .addrb(out_rp), .doutb(out_dout), .regceb(1'b1), .rstb(1'b0),
        .sbiterrb(), .dbiterrb()
    );

    // ------------------------------------------------------------------ crossings
    logic [31:0] cmd_d;
    logic        cmd_req;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_cmd (
        .src_clk(clk_25), .src_in(cmd_r), .src_send(sending), .src_rcv(src_rcv),
        .dest_clk(clk_dp), .dest_out(cmd_d), .dest_req(cmd_req), .dest_ack(1'b0));

    logic        msg_sending, msg_rcv;
    logic [15:0] msg_r;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(16)) u_msg (
        .src_clk(clk_dp), .src_in(msg_r), .src_send(msg_sending), .src_rcv(msg_rcv),
        .dest_clk(clk_25), .dest_out(msg_d), .dest_req(msg_req), .dest_ack(1'b0));

    // ------------------------------------------------------------------ clk_dp side
    assign res_we = v_out && (res_left != 11'd0);

    always_ff @(posedge clk_dp) begin
        dclr <= 1'b0;
        if (rst_dp) begin
            iss_left <= '0; res_left <= '0; rv <= 1'b0; pend_done <= 1'b0; pend_ack <= 1'b0;
            msg_sending <= 1'b0; dclr <= 1'b1; sat_acc <= '0;
        end else begin
            // issue reads of the input memory (one per clock)
            rv <= (iss_left != 11'd0);
            if (iss_left != 11'd0) begin
                in_addr  <= in_addr + 10'd1;
                iss_left <= iss_left - 11'd1;
            end
            // collect results
            if (res_we) begin
                out_wp   <= out_wp + 10'd1;
                res_left <= res_left - 11'd1;
                if (sat_out) sat_acc <= sat_acc + 11'd1;
                if (res_left == 11'd1) pend_done <= 1'b1;
            end
            // message sender (handshake to clk_25)
            if (!msg_sending) begin
                if (!msg_rcv) begin
                    if (pend_ack) begin
                        msg_r <= 16'h8000; msg_sending <= 1'b1; pend_ack <= 1'b0;
                    end else if (pend_done) begin
                        msg_r <= {5'd0, sat_acc}; msg_sending <= 1'b1; pend_done <= 1'b0;
                    end
                end
            end else if (msg_rcv) begin
                msg_sending <= 1'b0;
            end
            // commands
            if (cmd_req) begin
                if (cmd_d[31]) begin
                    iss_left <= '0; res_left <= '0; rv <= 1'b0; pend_done <= 1'b0; pend_ack <= 1'b1;
                    dclr <= 1'b1;
                end else begin
                    in_addr <= cmd_d[30:21]; out_wp <= cmd_d[20:11];
                    iss_left <= cmd_d[10:0]; res_left <= cmd_d[10:0]; sat_acc <= '0;
                end
            end
        end
    end

    fir_datapath u_dp (
        .clk(clk_dp), .clr(dclr), .v_in(rv), .x_in(in_dout),
        .v_out(v_out), .y_out(y_out), .sat_out(sat_out));
endmodule
