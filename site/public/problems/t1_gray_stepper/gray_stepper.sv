// gray_stepper.sv: 10-bit binary count shown as reflected Gray code, stepped by
// debounced BTNU presses and by an automatic rate, for t1_gray_stepper.
module gray_stepper #(
    parameter int DEBOUNCE_CYCLES = 1_000_000,
    parameter int TICK_CYCLES     = 100_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn,
    input  logic        dir_async,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_GRAY = 7'h00, R_BIN = 7'h01, R_CTRL = 7'h02, R_RATE = 7'h03, R_STEPS = 7'h04;
    localparam int PW = $clog2(TICK_CYCLES + 1);

    logic          lvl, press, dir, auto_on, run, astep, step;
    logic [9:0]    bin, gray, bin_nx;
    logic [15:0]   rate, tk, steps;
    logic [PW-1:0] pre;

    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db (.clk(clk), .rst(rst), .d_async(btn), .level(lvl), .rise(press));
    sync2 u_dir (.clk(clk), .rst(rst), .d(dir_async), .q(dir));

    wire wr_bin  = win_wr && win_addr == R_BIN;
    wire wr_ctrl = win_wr && win_addr == R_CTRL;
    wire wr_rate = win_wr && win_addr == R_RATE;

    assign run    = auto_on && rate != 16'd0;
    assign astep  = run && !wr_ctrl && !wr_rate && pre == PW'(TICK_CYCLES - 1) && tk == rate - 16'd1;
    assign step   = press || astep;
    assign bin_nx = dir ? bin - 10'd1 : bin + 10'd1;

    always_ff @(posedge clk) begin
        if (rst) begin
            pre <= '0; tk <= '0; auto_on <= 1'b0; rate <= 16'd250;
        end else begin
            if (wr_ctrl) auto_on <= win_wdata[0];
            if (wr_rate) rate <= win_wdata[15:0];
            if (wr_ctrl || wr_rate || !run) begin
                pre <= '0;
                tk  <= '0;
            end else if (pre == PW'(TICK_CYCLES - 1)) begin
                pre <= '0;
                tk  <= (tk == rate - 16'd1) ? 16'd0 : tk + 16'd1;
            end else begin
                pre <= pre + 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            bin <= '0; gray <= '0; steps <= '0;
        end else if (wr_bin) begin
            bin  <= win_wdata[9:0];
            gray <= win_wdata[9:0] ^ (win_wdata[9:0] >> 1);
        end else if (step) begin
            bin   <= bin_nx;
            gray  <= bin_nx ^ (bin_nx >> 1);
            steps <= steps + 1'b1;
        end
    end

`ifdef FORMAL
    // REQ-01: a step (no BIN write) changes exactly one bit of the Gray register.
    logic past_valid = 1'b0;
    always_ff @(posedge clk) past_valid <= 1'b1;
    always_ff @(posedge clk)
        if (past_valid && !$past(rst) && !rst && $past(step) && !$past(wr_bin))
            assert ($countones(gray ^ $past(gray)) == 1);
    always_comb assert (rst || gray == (bin ^ (bin >> 1)));
`endif

    assign led = {auto_on, 5'd0, gray};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_GRAY:  win_rdata <= {22'd0, gray};
                R_BIN:   win_rdata <= {22'd0, bin};
                R_CTRL:  win_rdata <= {23'd0, dir, 7'd0, auto_on};
                R_RATE:  win_rdata <= {16'd0, rate};
                R_STEPS: win_rdata <= {16'd0, steps};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
