// Register core of the glitch-free clock mux: registers, switch control, gate timer,
// BUFGCTRL clock mux and the self-checking muxed domain.
/* verilator lint_off DECLFILENAME */
// jtag_bus (supplied, read-only) has unused tdo / cmd_s[45]; unused-signal lint is off for files read after this one
/* verilator lint_off UNUSEDSIGNAL */
module clkmux_core #(
    parameter int unsigned DESIGN_ID        = 546701313,
    parameter int unsigned B_DIV            = 1,
    parameter int unsigned GATE_LEN_DEFAULT = 25000000
) (
    input  logic        clk,          // 25 MHz, clock A and register bus clock
    input  logic        rst,          // active high, synchronous to clk
    input  logic        clk_b,        // clock B (BUFG_GT output)
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int unsigned SW_MIN = 16;

    // ---------------- BUILD word ----------------
    logic [31:0] build_word;
`ifdef SYNTHESIS
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
`else
    assign build_word = 32'd0;
`endif

    // ---------------- registers (clk) ----------------
    logic [31:0] scratch, gate_len, sw_cnt, freq_count, mux_count, err_s;
    /* verilator lint_off SYNCASYNCNET */
    logic        sel, switching, sel_ctl, act_s, busy, done, gate, snap_tgl;
    /* verilator lint_on SYNCASYNCNET */
    logic [4:0]  timer;
    logic [31:0] remain;
    logic        f_req, s_req, f_rcv_unused;
    logic [31:0] f_out, s_out;

    // ---------------- clock mux ----------------
    logic clk_mux;
    logic sel_n;
    assign sel_n = ~sel_ctl;
    logic bg_one, bg_zero;
    assign bg_one  = 1'b1;
    assign bg_zero = 1'b0;
    BUFGCTRL u_bufgctrl (.O(clk_mux), .CE0(bg_one), .CE1(bg_one), .I0(clk), .I1(clk_b), .IGNORE0(bg_zero), .IGNORE1(bg_zero), .S0(sel_n), .S1(sel_ctl));

    // ---------------- crossings clk -> clk_mux ----------------
    logic rst_mux, sel_m, gate_m, snap_m, act_m;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_mux (
        .src_arst(rst), .dest_clk(clk_mux), .dest_arst(rst_mux));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_sel (
        .src_clk(clk), .src_in(sel_ctl), .dest_clk(clk_mux), .dest_out(sel_m));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate (
        .src_clk(clk), .src_in(gate), .dest_clk(clk_mux), .dest_out(gate_m));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_snap (
        .src_clk(clk), .src_in(snap_tgl), .dest_clk(clk_mux), .dest_out(snap_m));

    // ---------------- muxed domain ----------------
    logic [31:0] err_cnt, s_in, f_in;
    logic        s_send, f_send, s_rcv, f_rcv;
    p6_mux_domain u_dom (
        .clk_mux(clk_mux), .rst_mux(rst_mux), .gate_m(gate_m), .snap_tgl_m(snap_m),
        .sel_m(sel_m), .s_rcv(s_rcv), .f_rcv(f_rcv), .act_m(act_m), .err_cnt(err_cnt),
        .s_send(s_send), .s_in(s_in), .f_send(f_send), .f_in(f_in));

    // ---------------- crossings clk_mux -> clk ----------------
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_act (
        .src_clk(clk_mux), .src_in(act_m), .dest_clk(clk), .dest_out(act_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_err (
        .src_clk(clk_mux), .src_in_bin(err_cnt), .dest_clk(clk), .dest_out_bin(err_s));
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(2), .WIDTH(32)) u_freq (
        .src_clk(clk_mux), .src_in(f_in), .src_send(f_send), .src_rcv(f_rcv),
        .dest_clk(clk), .dest_req(f_req), .dest_ack(1'b0), .dest_out(f_out));
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(2), .WIDTH(32)) u_snapx (
        .src_clk(clk_mux), .src_in(s_in), .src_send(s_send), .src_rcv(s_rcv),
        .dest_clk(clk), .dest_req(s_req), .dest_ack(1'b0), .dest_out(s_out));

    assign f_rcv_unused = 1'b0;
    assign sfp_tx_disable = 1'b1;
    assign led = {|err_s, act_s};

    // ---------------- control ----------------
    always_ff @(posedge clk) begin
        if (rst) begin
            scratch <= '0; sel <= 1'b0; gate_len <= 32'(GATE_LEN_DEFAULT);
            switching <= 1'b0; sel_ctl <= 1'b0; timer <= '0; sw_cnt <= '0;
            busy <= 1'b0; done <= 1'b0; gate <= 1'b0; remain <= '0; freq_count <= '0;
            mux_count <= '0; snap_tgl <= 1'b0;
        end else begin
            // register writes
            if (h_we) begin
                case (h_addr)
                    12'h008: scratch  <= h_wdata;
                    12'h010: sel      <= h_wdata[0];
                    12'h01C: gate_len <= h_wdata;
                    12'h020: if (h_wdata[0] && !busy) begin
                        busy <= 1'b1; done <= 1'b0; gate <= 1'b1;
                        remain <= (gate_len == 32'd0) ? 32'd1 : gate_len;
                    end
                    12'h038: snap_tgl <= ~snap_tgl;
                    default: ;
                endcase
            end
            // switch control
            if (!switching) begin
                if (sel != act_s) begin
                    sel_ctl <= sel; switching <= 1'b1; timer <= 5'(SW_MIN - 1);
                end
            end else begin
                if (timer != 5'd0) timer <= timer - 5'd1;
                else if (act_s == sel_ctl) begin
                    switching <= 1'b0; sw_cnt <= sw_cnt + 32'd1;
                end
            end
            // gate timer
            if (gate && !(h_we && h_addr == 12'h020)) begin
                if (remain <= 32'd1) gate <= 1'b0;
                else remain <= remain - 32'd1;
            end
            if (f_req) begin freq_count <= f_out; done <= 1'b1; busy <= 1'b0; end
            if (s_req) mux_count <= s_out;
        end
    end

    // ---------------- read path ----------------
    always_ff @(posedge clk) begin
        if (rst) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= 32'(DESIGN_ID);
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {31'd0, sel};
                12'h014: h_rdata <= {30'd0, act_s, switching};
                12'h018: h_rdata <= 32'(B_DIV);
                12'h01C: h_rdata <= gate_len;
                12'h020: h_rdata <= 32'd0;
                12'h024: h_rdata <= {30'd0, done, busy};
                12'h028: h_rdata <= freq_count;
                12'h02C: h_rdata <= err_s;
                12'h030: h_rdata <= mux_count;
                12'h034: h_rdata <= sw_cnt;
                default: h_rdata <= 32'd0;
            endcase
        end
    end
endmodule
