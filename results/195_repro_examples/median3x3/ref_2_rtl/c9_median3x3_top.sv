// c9_median3x3_top: 3x3 median filter behind the UART test shell.
// Register window offsets (win_addr): 0 MASK, 1 GO, 2 STATUS, 3 NOUT, 4 VMASK,
// 0x10..0x27 window words, 0x30..0x37 MED0..7.
module c9_median3x3_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT
);
    localparam logic [31:0] DESIGN_ID = 32'h4D45444E;

    logic rst;
    reset_sync u_rs (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        win_rd;     // read data is registered every clock; the pulse is not needed
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_wdata;
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ---------------- state ----------------
    logic [71:0] win_q [8];
    logic [31:0] mask_q, vmask_q;
    logic [7:0]  med_q [8];
    logic [3:0]  count_q;
    logic        running_q, done_q;
    logic [5:0]  cnt_q;
    logic [3:0]  nxt_q;          // next window index to present (0..8)
    logic [71:0] cur_px;         // window for index nxt_q, registered

    wire go_w = win_wr && (win_addr == 7'h01);

    // ---------------- sequencer ----------------
    logic present;
    assign present = running_q && !cnt_q[5] && mask_q[cnt_q[4:0]] && !nxt_q[3];

    logic [3:0] nxt_d;
    always_comb begin
        nxt_d = nxt_q;
        if (go_w) nxt_d = 4'd0;
        else if (present) nxt_d = nxt_q + 4'd1;
    end

    logic       core_v;
    logic [7:0] core_med;
    median_core u_core (
        .clk(CLK100MHZ), .rst(rst), .in_valid(present), .in_win(cur_px),
        .out_valid(core_v), .out_med(core_med));

    always_ff @(posedge CLK100MHZ) begin
        cur_px <= win_q[nxt_d[2:0]];
        if (rst) begin
            mask_q    <= '0;
            vmask_q   <= '0;
            count_q   <= '0;
            running_q <= 1'b0;
            done_q    <= 1'b0;
            cnt_q     <= '0;
            nxt_q     <= '0;
            for (int i = 0; i < 8; i++) begin
                win_q[i] <= '0;
                med_q[i] <= '0;
            end
        end else begin
            nxt_q <= nxt_d;
            if (win_wr && win_addr == 7'h00) mask_q <= win_wdata;
            for (int k = 0; k < 8; k++)
                for (int j = 0; j < 3; j++)
                    if (win_wr && win_addr == 7'(16 + 3*k + j))
                        win_q[k][24*j +: 24] <= win_wdata[23:0];

            if (running_q) begin
                cnt_q <= cnt_q + 6'd1;
                if (core_v) begin
                    count_q <= count_q + 4'd1;
                    if (!count_q[3]) med_q[count_q[2:0]] <= core_med;
                    vmask_q[cnt_q[4:0] - 5'd1] <= 1'b1;
                end
                if (cnt_q == 6'd63) begin
                    running_q <= 1'b0;
                    done_q    <= 1'b1;
                end
            end

            if (go_w) begin
                vmask_q   <= '0;
                count_q   <= '0;
                done_q    <= 1'b0;
                running_q <= 1'b1;
                cnt_q     <= '0;
                for (int i = 0; i < 8; i++) med_q[i] <= '0;
            end
        end
    end

    // ---------------- read mux (registered) ----------------
    logic [31:0] rd_c;
    always_comb begin
        rd_c = '0;
        if (win_addr == 7'h00) rd_c = mask_q;
        if (win_addr == 7'h02) rd_c = {31'd0, done_q};
        if (win_addr == 7'h03) rd_c = {28'd0, count_q};
        if (win_addr == 7'h04) rd_c = vmask_q;
        for (int k = 0; k < 8; k++) begin
            for (int j = 0; j < 3; j++)
                if (win_addr == 7'(16 + 3*k + j)) rd_c = {8'd0, win_q[k][24*j +: 24]};
            if (win_addr == 7'(48 + k)) rd_c = {24'd0, med_q[k]};
        end
    end

    always_ff @(posedge CLK100MHZ) win_rdata <= rd_c;
endmodule
