// lfsr_dice.sv: 16-bit Galois LFSR with settable taps and seed, step bursts,
// and debounced BTNC rolls of (state mod 6) + 1, for t1_lfsr_dice.
module lfsr_dice #(
    parameter int DEBOUNCE_CYCLES = 1_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn,
    output logic [2:0]  roll,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_STATE = 7'h00, R_SEED = 7'h01, R_TAPS = 7'h02, R_ROLL = 7'h03,
                           R_HIST = 7'h04, R_STEP = 7'h05, R_ROLLS = 7'h06;

    logic        lvl, press;
    logic [15:0] s, seed, taps, hist, left, rolls, ns;

    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db (.clk(clk), .rst(rst), .d_async(btn), .level(lvl), .rise(press));

    function automatic logic [15:0] lstep(input logic [15:0] v, input logic [15:0] t);
        logic [15:0] r;
        r = v >> 1;
        if (v[0]) r = r ^ t;
        if (r == 16'd0) r = 16'd1;
        return r;
    endfunction

    assign ns = lstep(s, taps);

    wire wr_seed = win_wr && win_addr == R_SEED;
    wire wr_step = win_wr && win_addr == R_STEP;
    wire busy    = left != 16'd0;

    always_ff @(posedge clk) begin
        if (rst) begin
            s <= 16'hACE1; seed <= 16'hACE1; taps <= 16'hB400; roll <= '0; hist <= '0; left <= '0; rolls <= '0;
        end else begin
            if (win_wr && win_addr == R_TAPS) taps <= win_wdata[15:0];
            if (wr_seed) begin
                seed <= win_wdata[15:0];
                s    <= (win_wdata[15:0] == 16'd0) ? 16'd1 : win_wdata[15:0];
                left <= '0;
            end else if (busy) begin
                s    <= ns;
                left <= wr_step ? win_wdata[15:0] : left - 16'd1;
            end else begin
                if (wr_step) left <= win_wdata[15:0];
                if (press) begin
                    s     <= ns;
                    roll  <= 3'(ns % 16'd6) + 3'd1;
                    hist  <= {hist[11:0], 1'b0, 3'(ns % 16'd6) + 3'd1};
                    rolls <= rolls + 1'b1;
                end
            end
        end
    end

`ifdef FORMAL
    always_comb assert (rst || s != 16'd0);
`endif

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_STATE: win_rdata <= {16'd0, s};
                R_SEED:  win_rdata <= {16'd0, seed};
                R_TAPS:  win_rdata <= {16'd0, taps};
                R_ROLL:  win_rdata <= {29'd0, roll};
                R_HIST:  win_rdata <= {16'd0, hist};
                R_STEP:  win_rdata <= {16'd0, left};
                R_ROLLS: win_rdata <= {16'd0, rolls};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
