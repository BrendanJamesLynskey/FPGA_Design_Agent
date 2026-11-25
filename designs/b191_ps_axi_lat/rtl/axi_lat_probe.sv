// axi_lat_probe.sv: a register block on an AXI4 slave port that timestamps every access with a free-running counter (brief 191, board row B-R8).
//
// Purpose: measure the latency of the Arm Cortex-A53 accessing the programmable logic over AXI on the KR260 (Zynq UltraScale+ PS masters M_AXI_HPM0_FPD and M_AXI_HPM0_LPD).
// The processor system measures its own side with its generic timer; this block gives the fabric's view with the fabric clock: the clock in which each read request and each
// write was accepted. Software reads CNT twice and the difference of the two values is the time between the two read requests as the fabric saw them; software writes TRIG
// n times and reads the log of the clocks in which each write was accepted. All values are in fabric clocks (CLK_HZ); nothing here depends on software timer resolution.
//
// Protocol: AXI4, single-beat accesses only (what the processor issues for 32-bit accesses to Device memory: AxLEN = 0, AxSIZE = 2). An access with AxLEN != 0 or AxSIZE != 2
// is counted in BAD and answered as a single beat with SLVERR (the interconnect would wait for the other beats: software never does this). Registers are 32 bits; the low
// 12 bits of the address are decoded (a 4 KiB window), the upper bits are not (the interconnect decides what reaches the block). Unmapped reads return 0, unmapped writes are
// accepted and ignored (counted in BAD), read-only registers ignore writes (also counted in BAD). Write strobes: a write takes effect on a register only if all four strobes are set.
//
// Register map (byte offsets):
//   0x000 ID        RO  0x50534C54 ("PSLT")
//   0x004 BUILD     RO  parameter BUILD_ID (the build stamp the host script checks)
//   0x008 CLK_HZ    RO  parameter CLK_HZ (the fabric clock in Hz)
//   0x00C SCRATCH   RW  32 bits, reset 0: a place to write and read back (data path check)
//   0x010 CNT       RO  the counter value in the clock this read request was accepted (the clock arvalid && arready)
//   0x014 WR_TS     RO  the counter value in the clock the last write (to any address) was accepted (its AW and W both in)
//   0x018 WR_N      RO  the number of writes accepted since reset or CTRL.CLEAR
//   0x01C LOG_N     RO  the number of TRIG writes logged (saturates at LOG_DEPTH)
//   0x020 TRIG      WO  a write logs WR_TS into LOG[LOG_N] (nothing is logged once the log is full); reads return 0
//   0x024 CTRL      WO  bit 0 CLEAR: LOG_N, WR_N and BAD to 0 (the log's contents are not erased); reads return 0
//   0x028 BAD       RO  the number of accesses that were not single-beat 32-bit, unmapped, or writes to a read-only register
//   0x400 + 4 i  LOG[i]  RO  the clock of the i-th logged TRIG write
// Reset (synchronous, active low aresetn like every AXI port) clears the counter, the registers and the counts; the log memory is not cleared.
// Latency of the block itself: a read request is accepted in the clock arvalid is seen (arready is high whenever no read is pending) and the data is presented the clock after (rvalid);
// a write is accepted when AW and W are both in (they may arrive in either order or together) and its response (bvalid) is presented the clock after.
module axi_lat_probe #(
    parameter int          ID_W      = 16,
    parameter int          LOG_DEPTH = 256,                // a power of two, at most 256 (the window 0x400 to 0x7FC)
    parameter logic [31:0] BUILD_ID  = 32'hB191_0001,
    parameter logic [31:0] CLK_HZ    = 32'd100_000_000
) (
    input  logic            aclk,
    input  logic            aresetn,
    // write address, write data, write response
    input  logic [ID_W-1:0] awid,
    input  logic [31:0]     awaddr,
    input  logic [7:0]      awlen,
    input  logic [2:0]      awsize,
    input  logic            awvalid,
    output logic            awready,
    input  logic [31:0]     wdata,
    input  logic [3:0]      wstrb,
    input  logic            wlast,
    input  logic            wvalid,
    output logic            wready,
    output logic [ID_W-1:0] bid,
    output logic [1:0]      bresp,
    output logic            bvalid,
    input  logic            bready,
    // read address, read data
    input  logic [ID_W-1:0] arid,
    input  logic [31:0]     araddr,
    input  logic [7:0]      arlen,
    input  logic [2:0]      arsize,
    input  logic            arvalid,
    output logic            arready,
    output logic [ID_W-1:0] rid,
    output logic [31:0]     rdata,
    output logic [1:0]      rresp,
    output logic            rlast,
    output logic            rvalid,
    input  logic            rready
);
    localparam int LW = $clog2(LOG_DEPTH);
    logic [31:0] cnt, scratch, wr_ts, wr_n, log_n, bad;
    logic [31:0] log_mem [LOG_DEPTH];

    // ---- write channel: AW and W are held until both are in, then one write is made
    logic            aw_p, w_p;
    logic [ID_W-1:0] aw_id;
    logic [31:0]     aw_addr, w_data;
    logic [7:0]      aw_len;
    logic [2:0]      aw_size;
    logic [3:0]      w_strb;
    logic            commit;
    assign awready = !aw_p && !bvalid;
    assign wready  = !w_p && !bvalid;
    // the write is made in the clock both are present (a registered copy of one and the input of the other count as present)
    logic            have_aw, have_w;
    logic [ID_W-1:0] c_id;
    logic [31:0]     c_addr, c_data;
    logic [7:0]      c_len;
    logic [2:0]      c_size;
    logic [3:0]      c_strb;
    always_comb begin
        have_aw = aw_p || (awvalid && awready);
        have_w  = w_p  || (wvalid && wready);
        commit  = have_aw && have_w && !bvalid;
        c_id    = aw_p ? aw_id   : awid;
        c_addr  = aw_p ? aw_addr : awaddr;
        c_len   = aw_p ? aw_len  : awlen;
        c_size  = aw_p ? aw_size : awsize;
        c_data  = w_p  ? w_data  : wdata;
        c_strb  = w_p  ? w_strb  : wstrb;
    end
    logic        wr_bad, wr_ro;
    logic [11:0] w_off;
    assign w_off = c_addr[11:0];

    // ---- read channel
    logic            r_p;                      // a read response is waiting for rready
    logic [31:0]     r_data_q;
    logic [ID_W-1:0] r_id_q;
    logic [1:0]      r_resp_q;
    assign arready = !r_p;
    assign rvalid  = r_p;
    assign rdata   = r_data_q;
    assign rid     = r_id_q;
    assign rresp   = r_resp_q;
    assign rlast   = 1'b1;
    logic        rd_fire, rd_bad;
    logic [11:0] r_off;
    logic [31:0] rd_val;
    logic        rd_mapped;
    assign rd_fire = arvalid && arready;
    assign r_off   = araddr[11:0];
    always_comb begin
        rd_val = 32'd0; rd_mapped = 1'b1;
        case (r_off)
            12'h000: rd_val = 32'h5053_4C54;
            12'h004: rd_val = BUILD_ID;
            12'h008: rd_val = CLK_HZ;
            12'h00C: rd_val = scratch;
            12'h010: rd_val = cnt;                 // the counter in this clock: the clock the request was accepted
            12'h014: rd_val = wr_ts;
            12'h018: rd_val = wr_n;
            12'h01C: rd_val = log_n;
            12'h020, 12'h024: rd_val = 32'd0;
            12'h028: rd_val = bad;
            default: begin
                if (r_off >= 12'h400 && r_off < 12'(32'h400 + 4 * LOG_DEPTH)) rd_val = log_mem[r_off[LW+1:2]];
                else rd_mapped = 1'b0;
            end
        endcase
        rd_bad = (arlen != 8'd0) || (arsize != 3'd2) || !rd_mapped || (r_off[1:0] != 2'b00);
    end

    always_comb begin
        wr_ro  = 1'b0;
        case (w_off)
            12'h000, 12'h004, 12'h008, 12'h010, 12'h014, 12'h018, 12'h01C, 12'h028: wr_ro = 1'b1;
            default: ;
        endcase
        wr_bad = (c_len != 8'd0) || (c_size != 3'd2) || (c_strb != 4'hF) || wr_ro || (w_off[1:0] != 2'b00)
                 || !(w_off == 12'h00C || w_off == 12'h020 || w_off == 12'h024);
    end

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            cnt <= '0; scratch <= '0; wr_ts <= '0; wr_n <= '0; log_n <= '0; bad <= '0;
            aw_p <= 1'b0; w_p <= 1'b0; bvalid <= 1'b0; bid <= '0; bresp <= 2'b00;
            r_p <= 1'b0; r_data_q <= '0; r_id_q <= '0; r_resp_q <= 2'b00;
            aw_id <= '0; aw_addr <= '0; aw_len <= '0; aw_size <= '0; w_data <= '0; w_strb <= '0;
        end else begin
            cnt <= cnt + 32'd1;
            // write channel
            if (awvalid && awready && !commit) begin aw_p <= 1'b1; aw_id <= awid; aw_addr <= awaddr; aw_len <= awlen; aw_size <= awsize; end
            if (wvalid && wready && !commit) begin w_p <= 1'b1; w_data <= wdata; w_strb <= wstrb; end
            if (commit) begin
                aw_p <= 1'b0; w_p <= 1'b0;
                bvalid <= 1'b1; bid <= c_id; bresp <= wr_bad ? 2'b10 : 2'b00;
                wr_ts <= cnt; wr_n <= wr_n + 32'd1;
                if (!wr_bad) begin
                    if (w_off == 12'h00C) scratch <= c_data;
                    if (w_off == 12'h020 && log_n < 32'(LOG_DEPTH)) begin log_mem[log_n[LW-1:0]] <= cnt; log_n <= log_n + 32'd1; end
                    if (w_off == 12'h024 && c_data[0]) begin log_n <= '0; wr_n <= '0; end
                end
            end
            if (bvalid && bready) bvalid <= 1'b0;
            // read channel
            if (rd_fire) begin
                r_p <= 1'b1; r_data_q <= rd_val; r_id_q <= arid; r_resp_q <= rd_bad ? 2'b10 : 2'b00;
            end
            // the count of bad accesses: one for a bad write and one for a bad read, in the same clock too; CTRL.CLEAR zeroes it (and a bad read in that clock is counted after it)
            bad <= ((commit && !wr_bad && w_off == 12'h024 && c_data[0]) ? 32'd0 : bad) + 32'(commit && wr_bad) + 32'(rd_fire && rd_bad);
            if (r_p && rready) r_p <= 1'b0;
        end
    end
    logic unused;
    assign unused = &{1'b0, wlast, araddr[31:12], c_addr[31:12]};            // the window's upper address bits are not decoded (the interconnect decides what reaches the block)
endmodule
