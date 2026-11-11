// logic_analyser: register-mapped capture of WIDTH internal signals into block RAM (brief 30), read back through the
// test shell's window (shell/PROTOCOL.md). Level trigger ((sample & mask) == (value & mask)) or rising edge of any
// masked bit (EDGE=1 in CTRL); a pre-trigger depth; arm, status, read-back by address.
//
// Registers (win_addr, 32-bit):
//   0 CTRL      W: bit0 arm (self-clearing), bit1 edge mode, bit2 abort; R: same bits as last written (arm reads 0)
//   1 STATUS    R: [1:0] state (0 idle, 1 filling pre-trigger, 2 armed/waiting, 3 capturing post-trigger), bit2 done,
//                  [31:8] trigger position in samples (index in the buffer of the trigger sample)
//   2 MASK      RW: trigger mask (WIDTH bits)
//   3 VALUE     RW: trigger value
//   4 PRE       RW: samples kept before the trigger (0 .. DEPTH-1)
//   5 DEPTH     R: DEPTH
//   6 RD_ADDR   RW: read pointer (0 .. DEPTH-1); the buffer is a ring: sample 0 of the capture is at (TRIG_POS - PRE) mod DEPTH
//   7 RD_DATA   R: sample at RD_ADDR (WIDTH bits, zero-extended)
//   8 RAWCOUNT  R: samples written since arm
// A capture is DEPTH samples: PRE before the trigger sample, the trigger sample, DEPTH-1-PRE after it. After done,
// reading RD_DATA at RD_ADDR = k gives capture sample k (the block renumbers the ring for you).
/* verilator lint_off UNUSEDSIGNAL */   // the window bus is shared: not every address bit, read strobe or data bit is used here
module logic_analyser #(
    parameter int WIDTH   = 16,
    parameter int ADDR_W  = 10                 // DEPTH = 2**ADDR_W
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] sample,           // probed signals, registered in the capture domain
    input  logic             sample_en,        // 1 = take a sample this clock (decimation by the caller)
    input  logic [6:0]       win_addr,
    input  logic             win_wr,
    input  logic             win_rd,
    input  logic [31:0]      win_wdata,
    output logic [31:0]      win_rdata
);
    initial begin
        if (WIDTH < 1 || WIDTH > 32) $error("logic_analyser: WIDTH %0d outside 1..32", WIDTH);
        if (ADDR_W < 2 || ADDR_W > 14) $error("logic_analyser: ADDR_W %0d outside 2..14", ADDR_W);
    end
    localparam int DEPTH = 1 << ADDR_W;

    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [WIDTH-1:0] mask_r, value_r, prev;
    logic [ADDR_W-1:0] pre_r, wptr, rd_addr, trig_idx, start_idx;
    logic [ADDR_W:0]  filled, post_left;
    logic [31:0]      raw_count;
    logic [1:0]       state;
    logic             done, edge_mode;
    localparam logic [1:0] IDLE = 2'd0, FILL = 2'd1, WAIT = 2'd2, POST = 2'd3;

    logic hit;
    always_comb begin
        hit = edge_mode ? |((sample & ~prev) & mask_r) : ((sample & mask_r) == (value_r & mask_r));
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE; done <= 1'b0; wptr <= '0; mask_r <= '0; value_r <= '0; pre_r <= '0;
            rd_addr <= '0; edge_mode <= 1'b0; filled <= '0; post_left <= '0; raw_count <= '0; trig_idx <= '0;
            start_idx <= '0; prev <= '0;
        end else begin
            if (win_wr) begin
                case (win_addr[3:0])
                    4'd0: begin
                        edge_mode <= win_wdata[1];
                        if (win_wdata[2]) begin state <= IDLE; end
                        else if (win_wdata[0]) begin
                            state <= (pre_r == 0) ? WAIT : FILL; done <= 1'b0; wptr <= '0; filled <= '0; raw_count <= '0;
                        end
                    end
                    4'd2: mask_r  <= win_wdata[WIDTH-1:0];
                    4'd3: value_r <= win_wdata[WIDTH-1:0];
                    4'd4: pre_r   <= (32'(win_wdata[ADDR_W-1:0]) >= DEPTH - 1) ? ADDR_W'(DEPTH - 2) : win_wdata[ADDR_W-1:0];
                    4'd6: rd_addr <= win_wdata[ADDR_W-1:0];
                    default: ;
                endcase
            end
            if (sample_en) begin
                prev <= sample;
                if (state != IDLE) begin
                    mem[wptr] <= sample; wptr <= wptr + 1'b1; raw_count <= raw_count + 1'b1;
                end
                case (state)
                    FILL: begin
                        filled <= filled + 1'b1;
                        if (filled + 1 >= {1'b0, pre_r}) state <= WAIT;
                    end
                    WAIT: if (hit) begin
                        trig_idx  <= wptr;
                        start_idx <= wptr - pre_r;
                        post_left <= (ADDR_W+1)'(DEPTH - 1) - {1'b0, pre_r};
                        state     <= (DEPTH - 1 - 32'(pre_r) == 0) ? IDLE : POST;
                        done      <= (DEPTH - 1 - 32'(pre_r) == 0);
                    end
                    POST: begin
                        post_left <= post_left - 1'b1;
                        if (post_left == 1) begin state <= IDLE; done <= 1'b1; end
                    end
                    default: ;
                endcase
            end
        end
    end

    // read side is combinational on win_addr (stable while the host reads), so a parent can register it once
    always_comb begin
        case (win_addr[3:0])
            4'd0: win_rdata = {29'b0, 1'b0, edge_mode, 1'b0};
            4'd1: win_rdata = {{(24-ADDR_W){1'b0}}, trig_idx, 5'b0, done, state};
            4'd2: win_rdata = 32'(mask_r);
            4'd3: win_rdata = 32'(value_r);
            4'd4: win_rdata = 32'(pre_r);
            4'd5: win_rdata = 32'(DEPTH);
            4'd6: win_rdata = 32'(rd_addr);
            4'd7: win_rdata = 32'(mem[start_idx + rd_addr]);
            4'd8: win_rdata = raw_count;
            default: win_rdata = '0;
        endcase
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
