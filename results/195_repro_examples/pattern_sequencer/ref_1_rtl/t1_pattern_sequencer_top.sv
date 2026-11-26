// t1_pattern_sequencer_top: LED pattern sequencer with the UART test shell window.
module t1_pattern_sequencer_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 1000000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          DEBOUNCE_CYCLES = 2000000,
    parameter int          TICK_CYCLES     = 100000,
    parameter int          MAX_STEPS       = 16
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    localparam int TW = (TICK_CYCLES > 2) ? $clog2(TICK_CYCLES) : 1;

    logic clk, rst, press;
    assign clk = CLK100MHZ;

    reset_sync u_rs (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    btn_sync_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_db (
        .clk(clk), .rst(rst), .btn(BTNC), .press(press));

    // ---- shell window ------------------------------------------------------
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic [23:0] wdata;      // bits 31:24 of a write are ignored
    logic [23:0] rdata;      // bits 31:24 of every read are 0
    logic        unused_w;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h50534551), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign wdata     = win_wdata[23:0];
    assign win_rdata = {8'h00, rdata};
    assign unused_w  = &{1'b0, win_wdata[31:24], win_rd};

    // ---- entry memory ------------------------------------------------------
    logic [15:0] mem_pat [16];
    logic [7:0]  mem_dur [16];

    logic wr_entry;
    assign wr_entry = win_wr && (win_addr[6:4] == 3'd1);

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 16; i++) begin
                mem_pat[i] <= 16'h0;
                mem_dur[i] <= 8'h0;
            end
        end else if (wr_entry) begin
            mem_pat[win_addr[3:0]] <= wdata[15:0];
            mem_dur[win_addr[3:0]] <= wdata[23:16];
        end
    end

    // ---- sequencer ---------------------------------------------------------
    logic          run, paused, done, oneshot, show;
    logic [3:0]    index;
    logic [4:0]    length;
    logic [15:0]   loops;
    logic [TW-1:0] tick_cnt;
    logic [8:0]    ticks, cur_dur;

    logic        tick_hit, dur_end, last, ctrl_wr, len_ok;
    logic [8:0]  ticks_n;
    logic [4:0]  idx_n1;
    logic [3:0]  next_idx;
    logic [7:0]  next_dur_raw, start_dur_raw;

    assign ctrl_wr  = win_wr && (win_addr == 7'h00);
    assign len_ok   = (wdata[4:0] != 5'd0) && (wdata[4:0] <= 5'(MAX_STEPS));
    assign tick_hit = run && !paused && (tick_cnt == TW'(TICK_CYCLES - 1));
    assign ticks_n  = ticks + 9'd1;
    assign dur_end  = tick_hit && (ticks_n >= cur_dur);
    assign idx_n1   = {1'b0, index} + 5'd1;
    assign last     = (idx_n1 >= length);
    assign next_idx = last ? 4'd0 : idx_n1[3:0];
    assign next_dur_raw  = mem_dur[next_idx];
    assign start_dur_raw = mem_dur[0];

    always_ff @(posedge clk) begin
        if (rst) begin
            run     <= 1'b0;
            paused  <= 1'b0;
            done    <= 1'b0;
            oneshot <= 1'b0;
            show    <= 1'b0;
            index   <= 4'd0;
            length  <= 5'd4;
            loops   <= 16'd0;
        end else begin
            if (press && run) paused <= ~paused;

            if (dur_end) begin
                if (last) begin
                    loops <= loops + 16'd1;
                    if (oneshot) begin
                        run    <= 1'b0;
                        done   <= 1'b1;
                        paused <= 1'b0;
                    end else begin
                        index <= 4'd0;
                    end
                end else begin
                    index <= idx_n1[3:0];
                end
            end

            if (win_wr && win_addr == 7'h01 && len_ok) length <= wdata[4:0];

            if (ctrl_wr) begin
                oneshot <= wdata[1];
                paused  <= 1'b0;
                if (wdata[0]) begin
                    run   <= 1'b1;
                    done  <= 1'b0;
                    index <= 4'd0;
                    show  <= 1'b1;
                end else begin
                    run  <= 1'b0;
                    show <= 1'b0;
                end
            end
        end
    end

    // step timer datapath: only meaningful while run=1, so no reset
    always_ff @(posedge clk) begin
        if (ctrl_wr && wdata[0]) begin
            tick_cnt <= '0;
            ticks    <= 9'd0;
            cur_dur  <= (start_dur_raw == 8'd0) ? 9'd256 : {1'b0, start_dur_raw};
        end else if (run && !paused) begin
            if (tick_hit) begin
                tick_cnt <= '0;
                ticks    <= ticks_n;
                if (dur_end) begin
                    ticks   <= 9'd0;
                    cur_dur <= (next_dur_raw == 8'd0) ? 9'd256 : {1'b0, next_dur_raw};
                end
            end else begin
                tick_cnt <= tick_cnt + 1'b1;
            end
        end
    end

    // ---- LEDs: current entry's pattern straight from the memory --------------
    assign LED = show ? mem_pat[index] : 16'h0;

    // ---- register read mux (registered: data due one cycle after win_rd) -----
    always_ff @(posedge clk) begin
        rdata <= 24'h0;
        case (win_addr)
            7'h00:   rdata <= {22'h0, oneshot, run};
            7'h01:   rdata <= {19'h0, length};
            7'h02:   rdata <= {20'h0, index};
            7'h03:   rdata <= {21'h0, done, paused, run};
            7'h04:   rdata <= {8'h0, loops};
            default: if (win_addr[6:4] == 3'd1)
                         rdata <= {mem_dur[win_addr[3:0]], mem_pat[win_addr[3:0]]};
        endcase
    end
endmodule
