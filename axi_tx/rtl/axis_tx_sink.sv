// axis_tx_sink: the transactor's AXI4-Stream receiver and expected-data checker (brief 59A); see axis_tx_source.sv.
/* verilator lint_off UNUSEDSIGNAL */   // each end uses one byte of the throttle LFSR
module axis_tx_sink #(
    parameter int DATA_W = 32
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                clear,
    input  logic                exp_push,
    input  logic [15:0]         exp_len,
    input  logic [31:0]         exp_first,
    input  logic [DATA_W/8-1:0] exp_keep_last,
    input  logic                exp_no_last,
    output logic                exp_full,
    output logic                exp_empty,
    input  logic [31:0]         thr,
    input  logic [7:0]          ready_p,
    input  logic [DATA_W-1:0]   tdata,
    input  logic [DATA_W/8-1:0] tkeep,
    input  logic                tlast,
    input  logic                tvalid,
    output logic                tready,
    output logic [31:0]         beats,
    output logic [31:0]         pkts,
    output logic [31:0]         data_mism,
    output logic [31:0]         keep_mism,
    output logic [31:0]         last_mism,
    output logic [31:0]         unexpected,
    output logic [31:0]         first_mism      // bit 31 valid, [30:28] kind (1 data 2 keep 3 last 4 unexpected), [15:0] beat
);
    localparam int KW = DATA_W / 8;
    localparam int EW = 16 + 32 + KW + 1;
    logic [EW-1:0] q [16];
    logic [3:0]    wp = '0, rp = '0;
    logic [4:0]    cnt = '0;
    logic [15:0]   k = '0;                       // beat within the current expected packet
    initial begin
        beats = '0; pkts = '0; data_mism = '0; keep_mism = '0; last_mism = '0; unexpected = '0; first_mism = '0;
        for (int i = 0; i < 16; i++) q[i] = '0;
    end
    assign exp_full  = (cnt == 5'd16);
    assign exp_empty = (cnt == 5'd0);
    assign tready    = (thr[15:8] <= ready_p);
    wire [EW-1:0] h = q[rp];
    wire [15:0]   h_len  = (h[EW-1 -: 16] == 0) ? 16'd1 : h[EW-1 -: 16];
    wire [31:0]   h_first = h[KW+1 +: 32];
    wire [KW-1:0] h_kl   = h[1 +: KW];
    wire          h_nl   = h[0];
    wire          h_last = (k == h_len - 1'b1);
    wire [KW-1:0] ekeep  = h_last ? h_kl : {KW{1'b1}};
    wire [DATA_W-1:0] edata = {(DATA_W / 32){h_first + 32'(k)}};
    logic [DATA_W-1:0] bmask;
    always_comb for (int i = 0; i < KW; i++) bmask[8*i +: 8] = {8{ekeep[i]}};
    wire hs  = tvalid && tready;
    wire bad_data = ((tdata ^ edata) & bmask) != '0;
    wire bad_keep = (tkeep != ekeep);
    wire bad_last = (tlast != (h_last && !h_nl));
    wire pop = hs && !exp_empty && (h_last || tlast);
    wire push = exp_push && !exp_full;

    function automatic logic [31:0] sat(input logic [31:0] x);
        sat = (x == 32'hFFFF_FFFF) ? x : x + 1'b1;
    endfunction

    always_ff @(posedge clk) begin
        if (push) begin q[wp] <= {exp_len, exp_first, exp_keep_last, exp_no_last}; wp <= wp + 1'b1; end
        if (pop) rp <= rp + 1'b1;
        cnt <= cnt + (push ? 5'd1 : 5'd0) - (pop ? 5'd1 : 5'd0);
        if (hs && !exp_empty) k <= pop ? 16'd0 : k + 1'b1;
        if (clear) begin
            beats <= '0; pkts <= '0; data_mism <= '0; keep_mism <= '0; last_mism <= '0; unexpected <= '0; first_mism <= '0;
        end else if (hs) begin
            beats <= sat(beats);
            if (tlast) pkts <= sat(pkts);
            if (exp_empty) begin
                unexpected <= sat(unexpected);
                if (!first_mism[31]) first_mism <= {1'b1, 3'd4, 12'd0, 16'd0};
            end else begin
                if (bad_data) data_mism <= sat(data_mism);
                if (bad_keep) keep_mism <= sat(keep_mism);
                if (bad_last) last_mism <= sat(last_mism);
                if (!first_mism[31] && (bad_data || bad_keep || bad_last))
                    first_mism <= {1'b1, bad_data ? 3'd1 : bad_keep ? 3'd2 : 3'd3, 12'd0, k};
            end
        end
        if (rst || clear) begin wp <= '0; rp <= '0; cnt <= '0; k <= '0; end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
