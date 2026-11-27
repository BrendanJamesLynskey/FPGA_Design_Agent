// rp_patgen_regs: register file for the whole map. Live registers are written
// at the access edge and reset synchronously (rst active high). START copies
// the shape registers into the sequencer copies (run_*, r_pat) and clamps
// WIDTH into 1 to PERIOD-1 in the live register.
// Word index idx = offset / 4: 0 ID, 1 SCRATCH, 2 CTRL, 3 MODE, 4 PERIOD,
// 5 WIDTH, 6 LEVEL_HI, 7 LEVEL_LO, 8 COUNT, 9 LIMIT, 10 STATUS,
// 11 PERIODS_DONE, 12 PAT_LEN, 13 SAMPLE_DIV, 16 to 31 PAT0 to PAT15.
module rp_patgen_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [4:0]  idx,
    input  logic        wr_en,
    input  logic [31:0] wdata,
    output logic [31:0] rd_val,
    input  logic        running,
    input  logic        done,
    input  logic        clamped,
    input  logic [31:0] pdone,
    output logic        start_eff,
    output logic        stop_req,
    output logic [12:0] limit,
    input  logic [3:0]  pat_idx,
    output logic [13:0] pat_val,
    output logic        run_mode,
    output logic [31:0] run_period,
    output logic [31:0] run_width,
    output logic [13:0] run_hi,
    output logic [13:0] run_lo,
    output logic [15:0] run_count,
    output logic        run_cont,
    output logic [4:0]  run_pat_len,
    output logic [15:0] run_div
);
    logic [31:0] scratch;
    logic [31:0] period;
    logic [31:0] width;
    logic [13:0] level_hi;
    logic [13:0] level_lo;
    logic [15:0] count;
    logic [4:0]  pat_len;
    logic [15:0] sample_div;
    logic        mode;
    logic        cont;
    logic [13:0] pat   [0:15];
    logic [13:0] r_pat [0:15];

    logic [31:0] width_clamped;
    logic        cont_we;

    // CTRL decode: START and STOP are write-one-to-perform, not stored.
    wire is_ctrl = wr_en & (idx == 5'd2);
    assign stop_req  = is_ctrl & wdata[1];
    assign start_eff = is_ctrl & wdata[0] & ~running & ~wdata[1];
    // START while RUNNING changes nothing, CONT included
    assign cont_we  = is_ctrl & ~(wdata[0] & running & ~wdata[1]);

    // WIDTH clamp at START: nearest legal value in 1 to PERIOD-1
    wire [31:0] pm1 = period - 32'd1;
    always_comb begin
        if (width == 32'd0)
            width_clamped = 32'd1;
        else if (width > pm1)
            width_clamped = pm1;
        else
            width_clamped = width;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch    <= 32'd0;
            mode       <= 1'b0;
            period     <= 32'd1250;
            width      <= 32'd625;
            level_hi   <= 14'd2048;
            level_lo   <= 14'd0;
            count      <= 16'd1;
            limit      <= 13'd4096;
            pat_len    <= 5'd16;
            sample_div <= 16'd1;
            cont       <= 1'b0;
            for (int k = 0; k < 16; k++) pat[k] <= 14'd0;
        end else begin
            if (start_eff) width <= width_clamped;
            if (cont_we)   cont  <= wdata[2];
            if (wr_en) begin
                case (idx)
                    5'd1:  scratch <= wdata;
                    5'd3:  mode    <= (wdata[1:0] == 2'd1);
                    5'd4:  period  <= (wdata[31:1] == 31'd0) ? 32'd2 : wdata;
                    5'd5:  width   <= wdata;
                    5'd6:  level_hi <= wdata[13:0];
                    5'd7:  level_lo <= wdata[13:0];
                    5'd8:  count   <= (wdata[31:16] != 16'd0) ? 16'hFFFF :
                                      ((wdata[15:0] == 16'd0) ? 16'd1 : wdata[15:0]);
                    5'd9:  limit   <= (wdata > 32'd7372) ? 13'd7372 : wdata[12:0];
                    5'd12: pat_len <= (wdata > 32'd16) ? 5'd16 :
                                      ((wdata[4:0] == 5'd0) ? 5'd1 : wdata[4:0]);
                    5'd13: sample_div <= (wdata[31:16] != 16'd0) ? 16'hFFFF :
                                         ((wdata[15:0] == 16'd0) ? 16'd1 : wdata[15:0]);
                    default: if (idx[4]) pat[idx[3:0]] <= wdata[13:0];
                endcase
            end
        end
    end

    // Shape copies latched at START (no reset: loaded before first use)
    always_ff @(posedge clk) begin
        if (start_eff) begin
            run_mode    <= mode;
            run_period  <= period;
            run_width   <= width_clamped;
            run_hi      <= level_hi;
            run_lo      <= level_lo;
            run_count   <= count;
            run_cont    <= wdata[2];
            run_pat_len <= pat_len;
            run_div     <= sample_div;
            for (int k = 0; k < 16; k++) r_pat[k] <= pat[k];
        end
    end

    assign pat_val = r_pat[pat_idx];

    // Read mux (combinational on the access index, registered by the bus)
    always_comb begin
        case (idx)
            5'd0:    rd_val = 32'hFDA10201;
            5'd1:    rd_val = scratch;
            5'd2:    rd_val = {29'd0, cont, 2'b00};
            5'd3:    rd_val = {31'd0, mode};
            5'd4:    rd_val = period;
            5'd5:    rd_val = width;
            5'd6:    rd_val = {{18{level_hi[13]}}, level_hi};
            5'd7:    rd_val = {{18{level_lo[13]}}, level_lo};
            5'd8:    rd_val = {16'd0, count};
            5'd9:    rd_val = {19'd0, limit};
            5'd10:   rd_val = {29'd0, clamped, done, running};
            5'd11:   rd_val = pdone;
            5'd12:   rd_val = {27'd0, pat_len};
            5'd13:   rd_val = {16'd0, sample_div};
            default: rd_val = idx[4] ? {{18{pat[idx[3:0]][13]}}, pat[idx[3:0]]} : 32'd0;
        endcase
    end
endmodule
