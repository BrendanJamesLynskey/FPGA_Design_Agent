// debounce_bank.sv: sixteen independent switch debouncers, per-switch change
// counts and selectable sticky edge flags, for t1_debounce_bank.
module debounce_bank #(
    parameter int DEBOUNCE_CYCLES = 2_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [15:0] sw_async,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_LEVEL = 7'h00, R_EDGES = 7'h01, R_RISE = 7'h02, R_FALL = 7'h03;

    logic [15:0]      lvl, lvl_d, rise, fall, edges, rise_en, fall_en, unused;
    logic [15:0][7:0] cnt;

    for (genvar k = 0; k < 16; k++) begin : g_db
        bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db (.clk(clk), .rst(rst), .d_async(sw_async[k]),
                                                      .level(lvl[k]), .rise(unused[k]));
    end

    assign rise = lvl & ~lvl_d;
    assign fall = ~lvl & lvl_d;

    always_ff @(posedge clk) begin
        if (rst) begin
            lvl_d <= '0; edges <= '0; rise_en <= 16'hFFFF; fall_en <= '0; cnt <= '0;
        end else begin
            lvl_d <= lvl;
            edges <= (edges & ~((win_wr && win_addr == R_EDGES) ? win_wdata[15:0] : 16'h0000))
                   | (rise & rise_en) | (fall & fall_en);
            if (win_wr && win_addr == R_RISE) rise_en <= win_wdata[15:0];
            if (win_wr && win_addr == R_FALL) fall_en <= win_wdata[15:0];
            for (int k = 0; k < 16; k++) begin
                if (win_wr && win_addr == 7'(4 + k / 4)) cnt[k] <= '0;
                else if (lvl[k] != lvl_d[k])            cnt[k] <= cnt[k] + 8'd1;
            end
        end
    end

    assign led = lvl_d;

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_LEVEL: win_rdata <= {16'd0, lvl_d};
                R_EDGES: win_rdata <= {16'd0, edges};
                R_RISE:  win_rdata <= {16'd0, rise_en};
                R_FALL:  win_rdata <= {16'd0, fall_en};
                7'h04:   win_rdata <= {cnt[3], cnt[2], cnt[1], cnt[0]};
                7'h05:   win_rdata <= {cnt[7], cnt[6], cnt[5], cnt[4]};
                7'h06:   win_rdata <= {cnt[11], cnt[10], cnt[9], cnt[8]};
                7'h07:   win_rdata <= {cnt[15], cnt[14], cnt[13], cnt[12]};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
