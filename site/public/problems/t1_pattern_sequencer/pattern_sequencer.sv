// pattern_sequencer.sv: 16-entry LED pattern/duration memory played in loop or
// one-shot mode, paused by BTNC, for t1_pattern_sequencer.
module pattern_sequencer #(
    parameter int DEBOUNCE_CYCLES = 1_000_000,
    parameter int TICK_CYCLES     = 100_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_CTRL = 7'h00, R_LEN = 7'h01, R_INDEX = 7'h02, R_STATUS = 7'h03, R_LOOPS = 7'h04;
    localparam int PW = $clog2(TICK_CYCLES + 1);

    logic [15:0]   pat [16];
    logic [7:0]    dur [16];
    logic          lvl, press, run, oneshot, paused, done;
    logic [4:0]    len;
    logic [3:0]    idx;
    logic [8:0]    left;            // ticks left in this entry, 1..256
    logic [15:0]   loops;
    logic [PW-1:0] pre;

    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db (.clk(clk), .rst(rst), .d_async(btn), .level(lvl), .rise(press));

    wire wr_entry = win_wr && win_addr[6:4] == 3'b001;
    wire wr_ctrl  = win_wr && win_addr == R_CTRL;
    wire tick     = pre == PW'(TICK_CYCLES - 1);

    function automatic logic [8:0] ticks(input logic [7:0] d);
        return (d == 8'd0) ? 9'd256 : {1'b0, d};
    endfunction

    initial for (int i = 0; i < 16; i++) begin pat[i] = '0; dur[i] = '0; end

    always_ff @(posedge clk)
        if (wr_entry) begin
            pat[win_addr[3:0]] <= win_wdata[15:0];
            dur[win_addr[3:0]] <= win_wdata[23:16];
        end

    always_ff @(posedge clk) begin
        if (rst) begin
            run <= 1'b0; oneshot <= 1'b0; paused <= 1'b0; done <= 1'b0; len <= 5'd4; idx <= '0;
            left <= '0; loops <= '0; pre <= '0;
        end else begin
            if (win_wr && win_addr == R_LEN && win_wdata[4:0] != 5'd0 && win_wdata[4:0] <= 5'd16)
                len <= win_wdata[4:0];
            if (wr_ctrl) oneshot <= win_wdata[1];
            if (wr_ctrl && !win_wdata[0]) begin
                run <= 1'b0; paused <= 1'b0; done <= 1'b0;
            end else if (wr_ctrl && !run) begin
                run <= 1'b1; paused <= 1'b0; done <= 1'b0; idx <= '0; pre <= '0;
                left <= ticks(dur[0]);
            end else if (run) begin
                if (press) paused <= !paused;
                if (!paused) begin
                    pre <= tick ? '0 : pre + 1'b1;
                    if (tick) begin
                        if (left != 9'd1) left <= left - 9'd1;
                        else if (5'(idx) + 5'd1 < len) begin
                            idx  <= idx + 4'd1;
                            left <= ticks(dur[idx + 4'd1]);
                        end else begin
                            loops <= loops + 1'b1;
                            if (oneshot) begin
                                run  <= 1'b0;
                                done <= 1'b1;
                            end else begin
                                idx  <= '0;
                                left <= ticks(dur[0]);
                            end
                        end
                    end
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) led <= '0;
        else     led <= (run || done) ? pat[idx] : 16'd0;
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            if (win_addr[6:4] == 3'b001) win_rdata <= {8'd0, dur[win_addr[3:0]], pat[win_addr[3:0]]};
            else case (win_addr)
                R_CTRL:   win_rdata <= {30'd0, oneshot, run};
                R_LEN:    win_rdata <= {27'd0, len};
                R_INDEX:  win_rdata <= {28'd0, idx};
                R_STATUS: win_rdata <= {29'd0, done, paused, run};
                R_LOOPS:  win_rdata <= {16'd0, loops};
                default:  win_rdata <= '0;
            endcase
        end
    end
endmodule
