// Register bus of rp_patgen (architecture block reg_bus).
// Decodes sys_addr[19:0] on 4-byte steps, holds the read-write registers, answers reads
// and writes with sys_ack one clock later, and flags unmapped, unaligned and read-only
// writes with sys_err. Internal reset is active high, synchronous.
module rp_reg_bus (
    input  logic               clk,
    input  logic               rst,          // active high, synchronous
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic        [31:0] sys_addr,     // only [19:0] decoded
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic        [31:0] sys_wdata,
    input  logic               sys_wen,
    input  logic               sys_ren,
    output logic        [31:0] sys_rdata,
    output logic               sys_err,
    output logic               sys_ack,
    // sequencer status (read-only registers)
    input  logic               running,
    input  logic               done,
    input  logic               clamped,
    input  logic        [31:0] periods,
    // WIDTH legalised at START by the sequencer
    input  logic               width_set,
    input  logic        [31:0] width_set_val,
    // CTRL strobes, valid in the clock of the write
    output logic               start_req,
    output logic               stop_req,
    // configuration registers (live values)
    output logic               cont,
    output logic               mode,
    output logic        [31:0] period,
    output logic        [31:0] width,
    output logic signed [13:0] lvl_hi,
    output logic signed [13:0] lvl_lo,
    output logic        [15:0] count,
    output logic        [12:0] limit,
    output logic        [4:0]  pat_len,
    output logic        [15:0] sample_div,
    output logic        [223:0] pat          // PAT(i) = pat[14*i +: 14]
);
    localparam logic [31:0] ID_VALUE  = 32'hFDA10201;
    localparam logic [31:0] LIMIT_MAX = 32'd7372;

    // ------------------------------------------------------------ decode
    wire [19:0] a       = sys_addr[19:0];
    wire [4:0]  o       = a[6:2];                 // register index
    wire        aligned = (a[1:0] == 2'b00);
    wire        in_map  = (a[19:7] == 13'd0) & aligned &
                          (o != 5'd14) & (o != 5'd15);   // 0x38, 0x3C are unmapped
    wire        is_ro   = (o == 5'd0) | (o == 5'd10) | (o == 5'd11);  // ID, STATUS, PERIODS_DONE
    wire        rd      = sys_ren & ~sys_wen;
    wire        wr_ok   = sys_wen & in_map & ~is_ro;
    wire        ctrl_wr = wr_ok & (o == 5'd2);

    assign start_req = ctrl_wr & sys_wdata[0];
    assign stop_req  = ctrl_wr & sys_wdata[1];

    // ------------------------------------------------ read-write registers
    logic [31:0] scratch;

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch    <= 32'd0;
            cont       <= 1'b0;
            mode       <= 1'b0;
            period     <= 32'd1250;
            width      <= 32'd625;
            lvl_hi     <= 14'sd2048;
            lvl_lo     <= 14'sd0;
            count      <= 16'd1;
            limit      <= 13'd4096;
            pat_len    <= 5'd16;
            sample_div <= 16'd1;
            pat        <= '0;
        end else begin
            // CONT is stored unless the START in the same write is ignored (running)
            if (ctrl_wr && !(sys_wdata[0] && running)) begin
                cont <= sys_wdata[2];
            end
            if (width_set) begin
                width <= width_set_val;
            end
            if (wr_ok) begin
                case (o)
                    5'd1:    scratch    <= sys_wdata;
                    5'd3:    mode       <= (sys_wdata == 32'd1);
                    5'd4:    period     <= (sys_wdata[31:1] == 31'd0) ? 32'd2 : sys_wdata;
                    5'd5:    width      <= sys_wdata;
                    5'd6:    lvl_hi     <= sys_wdata[13:0];
                    5'd7:    lvl_lo     <= sys_wdata[13:0];
                    5'd8:    count      <= (sys_wdata == 32'd0) ? 16'd1 :
                                            (sys_wdata[31:16] != 16'd0) ? 16'hFFFF : sys_wdata[15:0];
                    5'd9:    limit      <= (sys_wdata > LIMIT_MAX) ? 13'd7372 : sys_wdata[12:0];
                    5'd12:   pat_len    <= (sys_wdata == 32'd0) ? 5'd1 :
                                            (sys_wdata > 32'd16) ? 5'd16 : sys_wdata[4:0];
                    5'd13:   sample_div <= (sys_wdata == 32'd0) ? 16'd1 :
                                            (sys_wdata[31:16] != 16'd0) ? 16'hFFFF : sys_wdata[15:0];
                    default: ;
                endcase
                for (int k = 0; k < 16; k++) begin
                    if (o[4] && (o[3:0] == k[3:0])) begin
                        pat[14*k +: 14] <= sys_wdata[13:0];
                    end
                end
            end
        end
    end

    // ------------------------------------------------------------ read mux
    function automatic logic [31:0] sx14(input logic [13:0] v);
        sx14 = {{18{v[13]}}, v};
    endfunction

    logic [31:0] rd_val;
    always_comb begin
        rd_val = 32'd0;
        case (o)
            5'd0:    rd_val = ID_VALUE;
            5'd1:    rd_val = scratch;
            5'd2:    rd_val = {29'd0, cont, 2'b00};
            5'd3:    rd_val = {31'd0, mode};
            5'd4:    rd_val = period;
            5'd5:    rd_val = width;
            5'd6:    rd_val = sx14(lvl_hi);
            5'd7:    rd_val = sx14(lvl_lo);
            5'd8:    rd_val = {16'd0, count};
            5'd9:    rd_val = {19'd0, limit};
            5'd10:   rd_val = {29'd0, clamped, done, running};
            5'd11:   rd_val = periods;
            5'd12:   rd_val = {27'd0, pat_len};
            5'd13:   rd_val = {16'd0, sample_div};
            default: begin
                for (int k = 0; k < 16; k++) begin
                    if (o == 5'(16 + k)) rd_val = sx14(pat[14*k +: 14]);
                end
            end
        endcase
    end

    // ------------------------------------------------------------ response
    always_ff @(posedge clk) begin
        if (rst) begin
            sys_ack   <= 1'b0;
            sys_err   <= 1'b0;
            sys_rdata <= 32'd0;
        end else begin
            sys_ack   <= sys_wen | sys_ren;
            sys_err   <= (sys_wen & ~(in_map & ~is_ro)) | (rd & ~in_map);
            sys_rdata <= (rd & in_map) ? rd_val : 32'd0;
        end
    end
endmodule
