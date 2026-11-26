// Shell register bus: address decode, register file, read mux, error and acknowledge.
// Offsets 0x00 to 0x7C on 4-byte steps. A register write takes effect on the next
// clock; sys_ack and sys_err are registered (one clock after the strobe).
// Reset is active high (rst), inverted once in the top module. Synchronous only.
module bus_regs (
    input  logic         clk,
    input  logic         rst,
    input  logic [19:0]  addr,
    input  logic [31:0]  wdata,
    input  logic         wen,
    input  logic         ren,
    input  logic         running_i,
    input  logic         done_i,
    input  logic         clamped_i,
    input  logic [31:0]  periods_i,
    input  logic         start_go,
    output logic [31:0]  rdata_q,
    output logic         ack_q,
    output logic         err_q,
    output logic         start_req,
    output logic         stop_req,
    output logic [31:0]  period_o,
    output logic [31:0]  width_start_o,
    output logic         mode_o,
    output logic [15:0]  count_o,
    output logic [4:0]   patlen_o,
    output logic [15:0]  sdiv_o,
    output logic [13:0]  lvl_hi_o,
    output logic [13:0]  lvl_lo_o,
    output logic [12:0]  limit_o,
    output logic [223:0] pat_o
);
    // register index = addr[6:2]
    localparam logic [4:0] R_ID      = 5'd0;
    localparam logic [4:0] R_SCRATCH = 5'd1;
    localparam logic [4:0] R_CTRL    = 5'd2;
    localparam logic [4:0] R_MODE    = 5'd3;
    localparam logic [4:0] R_PERIOD  = 5'd4;
    localparam logic [4:0] R_WIDTH   = 5'd5;
    localparam logic [4:0] R_LVLHI   = 5'd6;
    localparam logic [4:0] R_LVLLO   = 5'd7;
    localparam logic [4:0] R_COUNT   = 5'd8;
    localparam logic [4:0] R_LIMIT   = 5'd9;
    localparam logic [4:0] R_STATUS  = 5'd10;
    localparam logic [4:0] R_PERIODS = 5'd11;
    localparam logic [4:0] R_PATLEN  = 5'd12;
    localparam logic [4:0] R_SDIV    = 5'd13;
    // 14 and 15 (0x38, 0x3C) have no register; 16 to 31 are PAT0 to PAT15

    logic [4:0]  ridx;
    logic        in_range, aligned, map_ok, ro;
    logic        rd_ok, wr_ok, ctrl_wr, err_c, pat_sel_w;
    logic [31:0] rmux;
    logic        cont_q, mode_q;
    logic [31:0] scratch_q, period_q, width_q;
    logic [13:0] lvl_hi_q, lvl_lo_q;
    logic [15:0] count_q, sdiv_q;
    logic [12:0] limit_q;
    logic [4:0]  patlen_q;
    logic [13:0] pat_q [0:15];
    logic [13:0] pat_rd;
    logic [31:0] pm1;
    logic [31:0] lvl_hi_ext, lvl_lo_ext, pat_ext;

    assign ridx     = addr[6:2];
    assign in_range = (addr[19:7] == 13'd0);
    assign aligned  = (addr[1:0] == 2'b00);
    assign map_ok   = in_range & aligned & (ridx != 5'd14) & (ridx != 5'd15);
    assign ro       = (ridx == R_ID) | (ridx == R_STATUS) | (ridx == R_PERIODS);
    assign rd_ok    = ren & ~wen & map_ok;
    assign wr_ok    = wen & ~ren & map_ok & ~ro;
    assign ctrl_wr  = wen & ~ren & map_ok & (ridx == R_CTRL);
    assign pat_sel_w = ridx[4];
    // STOP wins over START in the same write
    assign start_req = ctrl_wr & wdata[0] & ~wdata[1];
    assign stop_req  = ctrl_wr & wdata[1];
    // error: both strobes, write to unmapped or read-only, read of unmapped
    assign err_c = (wen & ren) | (wen & ~ren & (~map_ok | ro)) | (ren & ~wen & ~map_ok);

    // WIDTH as replaced at START: 0 becomes 1, above PERIOD-1 becomes PERIOD-1
    assign pm1 = period_q - 32'd1;
    assign width_start_o = (width_q == 32'd0) ? 32'd1 : ((width_q > pm1) ? pm1 : width_q);

    assign period_o = period_q;
    assign mode_o   = mode_q;
    assign count_o  = count_q;
    assign patlen_o = patlen_q;
    assign sdiv_o   = sdiv_q;
    assign lvl_hi_o = lvl_hi_q;
    assign lvl_lo_o = lvl_lo_q;
    assign limit_o  = limit_q;

    // sign extension of the signed 14-bit registers (continuous assigns)
    assign lvl_hi_ext = {{18{lvl_hi_q[13]}}, lvl_hi_q};
    assign lvl_lo_ext = {{18{lvl_lo_q[13]}}, lvl_lo_q};
    assign pat_rd     = pat_q[ridx[3:0]];
    assign pat_ext    = {{18{pat_rd[13]}}, pat_rd};

    genvar g;
    generate
        for (g = 0; g < 16; g++) begin : g_pat_out
            assign pat_o[g*14 +: 14] = pat_q[g];
        end
    endgenerate

    // read mux on the current (pre-edge) register values
    always_comb begin
        case (ridx)
            R_ID:      rmux = 32'hFDA10201;
            R_SCRATCH: rmux = scratch_q;
            R_CTRL:    rmux = {29'd0, cont_q, 2'b00};
            R_MODE:    rmux = {31'd0, mode_q};
            R_PERIOD:  rmux = period_q;
            R_WIDTH:   rmux = width_q;
            R_LVLHI:   rmux = lvl_hi_ext;
            R_LVLLO:   rmux = lvl_lo_ext;
            R_COUNT:   rmux = {16'd0, count_q};
            R_LIMIT:   rmux = {19'd0, limit_q};
            R_STATUS:  rmux = {29'd0, clamped_i, done_i, running_i};
            R_PERIODS: rmux = periods_i;
            R_PATLEN:  rmux = {27'd0, patlen_q};
            R_SDIV:    rmux = {16'd0, sdiv_q};
            default:   rmux = pat_ext;
        endcase
    end

    // register file, synchronous reset
    always_ff @(posedge clk) begin
        if (rst) begin
            scratch_q <= 32'd0;
            cont_q    <= 1'b0;
            mode_q    <= 1'b0;
            period_q  <= 32'd1250;
            width_q   <= 32'd625;
            lvl_hi_q  <= 14'd2048;
            lvl_lo_q  <= 14'd0;
            count_q   <= 16'd1;
            limit_q   <= 13'd4096;
            patlen_q  <= 5'd16;
            sdiv_q    <= 16'd1;
            for (int i = 0; i < 16; i++) pat_q[i] <= 14'd0;
            ack_q     <= 1'b0;
            err_q     <= 1'b0;
        end else begin
            ack_q <= wen | ren;
            err_q <= err_c;
            if (start_go) width_q <= width_start_o;
            if (wr_ok) begin
                case (ridx)
                    R_SCRATCH: scratch_q <= wdata;
                    R_CTRL:    cont_q    <= wdata[2];
                    R_MODE:    mode_q    <= wdata[0] & ~wdata[1];
                    R_PERIOD:  period_q  <= (wdata[31:1] == 31'd0) ? 32'd2 : wdata;
                    R_WIDTH:   width_q   <= wdata;
                    R_LVLHI:   lvl_hi_q  <= wdata[13:0];
                    R_LVLLO:   lvl_lo_q  <= wdata[13:0];
                    R_COUNT:   count_q   <= (wdata[15:0] == 16'd0) ? 16'd1 : wdata[15:0];
                    R_LIMIT:   limit_q   <= (wdata > 32'd7372) ? 13'd7372 : wdata[12:0];
                    R_PATLEN:  patlen_q  <= (wdata == 32'd0) ? 5'd1 :
                                            ((wdata > 32'd16) ? 5'd16 : wdata[4:0]);
                    R_SDIV:    sdiv_q    <= (wdata[15:0] == 16'd0) ? 16'd1 : wdata[15:0];
                    default: ;
                endcase
                if (pat_sel_w) pat_q[ridx[3:0]] <= wdata[13:0];
            end
        end
    end

    // read data: registered, zero unless a mapped register is read alone
    always_ff @(posedge clk) begin
        rdata_q <= (rd_ok & ~rst) ? rmux : 32'd0;
    end
endmodule
