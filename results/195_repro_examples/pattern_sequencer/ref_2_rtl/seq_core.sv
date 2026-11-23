// seq_core: register window, 16x24 step store and playback engine.
module seq_core #(
    parameter int TICK_CYCLES = 100000
) (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high
    input  logic        press,      // debounced BTNC rising edge
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,  // bits 31:24 unused (entry has 24 bits)
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam int PW = (TICK_CYCLES > 1) ? $clog2(TICK_CYCLES) : 1;

    logic [15:0] pat [16];
    logic [7:0]  dur [16];

    logic        run, oneshot, paused, done, hold;
    logic [4:0]  length;
    logic [3:0]  idx;
    logic [15:0] loops;
    logic [PW-1:0] pre;
    logic [8:0]  tick;

    // next state
    logic        run_n, oneshot_n, paused_n, done_n, hold_n;
    logic [3:0]  idx_n;
    logic [15:0] loops_n;
    logic [PW-1:0] pre_n;
    logic [8:0]  tick_n;

    wire        wr_ctrl  = win_wr && (win_addr == 7'h00);
    wire        wr_len   = win_wr && (win_addr == 7'h01);
    wire        wr_entry = win_wr && (win_addr[6:4] == 3'b001);
    wire [3:0]  wr_idx   = win_addr[3:0];
    wire [8:0]  cur_dur  = (dur[idx] == 8'd0) ? 9'd256 : {1'b0, dur[idx]};

    always_comb begin
        run_n     = run;
        oneshot_n = oneshot;
        paused_n  = paused;
        done_n    = done;
        hold_n    = hold;
        idx_n     = idx;
        loops_n   = loops;
        pre_n     = pre;
        tick_n    = tick;

        if (wr_ctrl) begin
            oneshot_n = win_wdata[1];
            paused_n  = 1'b0;
            hold_n    = 1'b0;
            if (win_wdata[0]) begin
                run_n  = 1'b1;
                done_n = 1'b0;
                idx_n  = 4'd0;
                pre_n  = '0;
                tick_n = 9'd0;
            end else begin
                run_n = 1'b0;
            end
        end else begin
            if (press && run) paused_n = !paused;
            if (run && !paused_n) begin
                if (int'(pre) + 1 >= TICK_CYCLES) begin
                    pre_n  = '0;
                    tick_n = tick + 9'd1;
                    if (tick_n >= cur_dur) begin
                        tick_n = 9'd0;
                        if ({1'b0, idx} + 5'd1 >= length) begin
                            loops_n = loops + 16'd1;
                            if (oneshot) begin
                                run_n    = 1'b0;
                                paused_n = 1'b0;
                                done_n   = 1'b1;
                                hold_n   = 1'b1;
                            end else begin
                                idx_n = 4'd0;
                            end
                        end else begin
                            idx_n = idx + 4'd1;
                        end
                    end
                end else begin
                    pre_n = pre + 1'b1;
                end
            end
        end
    end

    // LED pattern with write bypass so a write to the shown step lands in 1 clock
    wire [15:0] pat_sel = (wr_entry && wr_idx == idx_n) ? win_wdata[15:0] : pat[idx_n];
    wire [15:0] led_n   = (run_n || hold_n) ? pat_sel : 16'h0000;

    always_ff @(posedge clk) begin
        if (rst) begin
            run     <= 1'b0;
            oneshot <= 1'b0;
            paused  <= 1'b0;
            done    <= 1'b0;
            hold    <= 1'b0;
            idx     <= 4'd0;
            loops   <= 16'd0;
            pre     <= '0;
            tick    <= 9'd0;
            length  <= 5'd4;
            led     <= 16'd0;
            for (int i = 0; i < 16; i++) begin
                pat[i] <= 16'd0;
                dur[i] <= 8'd0;
            end
        end else begin
            run     <= run_n;
            oneshot <= oneshot_n;
            paused  <= paused_n;
            done    <= done_n;
            hold    <= hold_n;
            idx     <= idx_n;
            loops   <= loops_n;
            pre     <= pre_n;
            tick    <= tick_n;
            led     <= led_n;
            if (wr_len && win_wdata[4:0] >= 5'd1 && win_wdata[4:0] <= 5'd16)
                length <= win_wdata[4:0];
            if (wr_entry) begin
                pat[wr_idx] <= win_wdata[15:0];
                dur[wr_idx] <= win_wdata[23:16];
            end
        end
    end

    // read port: data valid the cycle after win_rd
    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'h0;
        end else if (win_rd) begin
            win_rdata <= 32'h0;
            if (win_addr[6:4] == 3'b001) begin
                win_rdata <= {8'h00, dur[win_addr[3:0]], pat[win_addr[3:0]]};
            end else begin
                case (win_addr)
                    7'h00:   win_rdata <= {30'h0, oneshot, run};
                    7'h01:   win_rdata <= {27'h0, length};
                    7'h02:   win_rdata <= {28'h0, idx};
                    7'h03:   win_rdata <= {29'h0, done, paused, run};
                    7'h04:   win_rdata <= {16'h0, loops};
                    default: win_rdata <= 32'h0;
                endcase
            end
        end
    end
endmodule
