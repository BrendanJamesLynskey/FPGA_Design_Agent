// Register core: registers, SEL/STATUS, switch counter, frequency gate, LEDs, BUFGCTRL clock mux,
// and the muxed (clk_mux) domain. Register port runs in clk.
module p6_clkmux_core #(
    parameter int unsigned DESIGN_ID               = 32'h20960001,
    parameter int unsigned B_DIV                   = 2,
    parameter int unsigned GATE_LEN_DEFAULT_CYCLES = 25000000,
    parameter int unsigned SYNC_STAGES             = 2
) (
    input  logic        clk,        // the 25 MHz clk register-port clock
    input  logic        clk_b,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- registers (clk) ----------------
    logic [31:0] scratch, gate_len, freq_count, mux_errs, mux_count, switch_count, build;
    logic        sel, act_c3, act_q, busy, done, waiting, gate_en;
    logic [31:0] remaining;

    logic [31:0] usr_data;
    logic        usr_valid, usr_cfgclk;
    USR_ACCESSE2 u_usr (.DATA(usr_data), .DATAVALID(usr_valid), .CFGCLK(usr_cfgclk));

    // ---------------- clock mux ----------------
    logic clk_mux;
    wire  sel_n = ~sel;
    wire clk_bd = clk_b;  // already divided by B_DIV in the top
    wire ce_hi  = 1'b1;
    wire ign_lo = 1'b0;
    BUFGCTRL #(.INIT_OUT(0), .PRESELECT_I0("TRUE"), .PRESELECT_I1("FALSE")) u_mux (
        .O(clk_mux),
        .I0(clk),
        .I1(clk_bd),
        .S0(sel_n),
        .S1(sel),
        .CE0(ce_hi),
        .CE1(ce_hi),
        .IGNORE0(ign_lo),
        .IGNORE1(ign_lo));

    // ---------------- muxed domain ----------------
    logic        rst_m, sel_m, gate_m, active_m;
    logic [31:0] ec_data_m, ec_data_c;
    logic        ec_send, ec_rcv, ec_req;
    logic [63:0] rep_data_m, rep_data_c;
    logic        rep_send, rep_rcv, rep_req;

    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_m (
        .src_arst(rst), .dest_clk(clk_mux), .dest_arst(rst_m));
    xpm_cdc_single #(.DEST_SYNC_FF(SYNC_STAGES + 1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_sel_m (
        .src_clk(clk), .src_in(sel), .dest_clk(clk_mux), .dest_out(sel_m));
    xpm_cdc_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate_m (
        .src_clk(clk), .src_in(gate_en), .dest_clk(clk_mux), .dest_out(gate_m));
    xpm_cdc_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_act_c (
        .src_clk(clk_mux), .src_in(active_m), .dest_clk(clk), .dest_out(act_c3));

    mux_domain u_mux_dom (
        .clk(clk_mux), .rst(rst_m), .sel_m(sel_m), .gate_m(gate_m), .active(active_m),
        .ec_data(ec_data_m), .ec_send(ec_send), .ec_rcv(ec_rcv),
        .rep_data(rep_data_m), .rep_send(rep_send), .rep_rcv(rep_rcv));

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(SYNC_STAGES), .WIDTH(32)) u_ec (
        .src_clk(clk_mux), .src_in(ec_data_m), .src_send(ec_send), .src_rcv(ec_rcv),
        .dest_clk(clk), .dest_out(ec_data_c), .dest_req(ec_req), .dest_ack(1'b0));
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(SYNC_STAGES), .WIDTH(64)) u_rep (
        .src_clk(clk_mux), .src_in(rep_data_m), .src_send(rep_send), .src_rcv(rep_rcv),
        .dest_clk(clk), .dest_out(rep_data_c), .dest_req(rep_req), .dest_ack(1'b0));

    // ---------------- register file ----------------
    wire wr_scratch = h_we && (h_addr == 12'h008);
    wire wr_sel     = h_we && (h_addr == 12'h010);
    wire wr_gate    = h_we && (h_addr == 12'h01C);
    wire wr_ctrl    = h_we && (h_addr == 12'h020);
    wire wr_snap    = h_we && (h_addr == 12'h038);

    logic [31:0] rd_mux;
    always_comb begin
        unique case (h_addr)
            12'h000: rd_mux = DESIGN_ID[31:0];
            12'h004: rd_mux = build;
            12'h008: rd_mux = scratch;
            12'h010: rd_mux = {31'd0, sel};
            12'h014: rd_mux = {30'd0, act_c3, sel != act_c3};
            12'h018: rd_mux = B_DIV[31:0];
            12'h01C: rd_mux = gate_len;
            12'h024: rd_mux = {30'd0, done, busy};
            12'h028: rd_mux = freq_count;
            12'h02C: rd_mux = mux_errs;
            12'h030: rd_mux = mux_count;
            12'h034: rd_mux = switch_count;
            default: rd_mux = 32'd0;
        endcase
    end

    always_ff @(posedge clk) begin
        build <= usr_data;
        if (h_re) h_rdata <= rd_mux;
        act_q <= act_c3;

        if (rst) begin
            scratch <= 32'd0; sel <= 1'b0; gate_len <= GATE_LEN_DEFAULT_CYCLES[31:0];
            freq_count <= 32'd0; mux_errs <= 32'd0; mux_count <= 32'd0; switch_count <= 32'd0;
            busy <= 1'b0; done <= 1'b0; waiting <= 1'b0; gate_en <= 1'b0;
            remaining <= 32'd0; h_rdata <= 32'd0; act_q <= 1'b0;
        end else begin
            if (wr_scratch) scratch  <= h_wdata;
            if (wr_sel)     sel      <= h_wdata[0];
            if (wr_gate)    gate_len <= h_wdata;

            if (act_c3 != act_q) switch_count <= switch_count + 32'd1;

            // frequency gate
            if (wr_ctrl && h_wdata[0] && !busy && !waiting) begin
                busy <= 1'b1; waiting <= 1'b1; done <= 1'b0; gate_en <= 1'b1; freq_count <= 32'd0;
                remaining <= (gate_len == 32'd0) ? 32'd1 : gate_len;
            end else if (busy) begin
                remaining <= remaining - 32'd1;
                if (remaining == 32'd0) begin busy <= 1'b0; gate_en <= 1'b0; end
            end
            if (ec_req) begin freq_count <= ec_data_c; done <= 1'b1; waiting <= 1'b0; end

            // report channel and snapshot
            // rep_data_c is held stable by the handshake between updates
            if (rep_req) mux_errs <= rep_data_c[63:32];
            if (wr_snap) mux_count <= rep_data_c[31:0];
        end
    end

    assign led = {sel, sel != act_c3};

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused = &{1'b0, usr_valid, usr_cfgclk};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
