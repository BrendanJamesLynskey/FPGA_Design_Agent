// fft_fastconv_axil: the AXI4-Lite register file of the fast-convolution block fft_fastconv_os (arith brief 161). It holds nothing but the coefficient-load registers and four status words;
// the filter spectrum itself lives in a RAM of the core, written through coef_we / coef_addr / coef_re / coef_im.
//
// Register map (32-bit registers, byte addresses; address bits [1:0] are ignored, so every access is a whole word; one outstanding transaction per channel):
//   0x00 ID        RO  0x46435631 ("FCV1")
//   0x04 CFG0      RO  [4:0] LOGN, [15:8] W, [31:16] L (taps)
//   0x08 CFG1      RO  [7:0] WH, [15:8] FH, [19:16] GB
//   0x0C STATUS    RW  [0] BUSY (RO: a block is in flight or the block memory is being cleared: coefficient commits are refused), [1] DROPPED (sticky: a commit was refused; write 1 to clear),
//                      [2] SAT (sticky: an output sample was saturated; write 1 to clear); other bits read 0 and ignore writes
//   0x10 BLOCKS    RO  the number of blocks started since reset (wraps at 2**32)
//   0x14 COEF_ADDR RW  the bin index of the next commit, [LOGN-1:0]; upper bits ignored on write and read as 0; incremented by every commit that is accepted (wraps at N)
//   0x18 COEF_RE   RW  the staged real part, WH bits (sign-extended on read)
//   0x1C COEF_IM   RW  writing it commits {staged real part, this value as the imaginary part (WH bits)} at COEF_ADDR, when BUSY is 0; reads return the last value written
// Responses: OKAY (2'b00) for an accepted access; SLVERR (2'b10) for a write to a read-only register, to an unmapped address (0x20 and above), with write strobes other than 4'b1111, or a COEF_IM commit
// refused because BUSY was 1 (it then sets DROPPED, changes nothing else, and COEF_ADDR does not advance); a read of an unmapped address returns 0 with SLVERR. A refused write has no other effect.
// Reads have no side effects. No access can hang the interface: every accepted request gets exactly one response.
// Same-clock priority: if the core's SAT pulse and a write-1-to-clear of SAT arrive in the same clock the sticky bit stays set.
//
// Handshakes: awready and wready are high when no response is pending and that channel's request has not been taken (so a master may present address and data in any order, or together); the write executes
// when both are held; bvalid stays up until bready. arready is high when no read response is pending; rvalid stays up until rready. No output depends combinationally on an input valid.
//
// Intended primitive use (stated before any Vivado run; not yet measured): about 70 flip-flops (the held address, data and strobes, the staged values, flags) and 40 LUTs of decode; no RAM, no DSP.
module fft_fastconv_axil #(
    parameter int LOGN = 8,
    parameter int L    = 33,
    parameter int W    = 16,
    parameter int WH   = 24,
    parameter int FH   = 14,
    parameter int GB   = 1
) (
    input  logic                clk,
    input  logic                aresetn,
    input  logic                s_axil_awvalid,
    output logic                s_axil_awready,
    // verilator lint_off UNUSEDSIGNAL
    input  logic [5:0]          s_axil_awaddr,      // bits [1:0] are ignored
    // verilator lint_on UNUSEDSIGNAL
    input  logic                s_axil_wvalid,
    output logic                s_axil_wready,
    input  logic [31:0]         s_axil_wdata,
    input  logic [3:0]          s_axil_wstrb,
    output logic                s_axil_bvalid,
    input  logic                s_axil_bready,
    output logic [1:0]          s_axil_bresp,
    input  logic                s_axil_arvalid,
    output logic                s_axil_arready,
    // verilator lint_off UNUSEDSIGNAL
    input  logic [5:0]          s_axil_araddr,      // bits [1:0] are ignored
    // verilator lint_on UNUSEDSIGNAL
    output logic                s_axil_rvalid,
    input  logic                s_axil_rready,
    output logic [31:0]         s_axil_rdata,
    output logic [1:0]          s_axil_rresp,
    input  logic                busy,
    input  logic                sat_pulse,
    input  logic [31:0]         blocks,
    output logic                coef_we,
    output logic [LOGN-1:0]     coef_addr,
    output logic [WH-1:0]       coef_re,
    output logic [WH-1:0]       coef_im
);
    localparam logic [1:0] OKAY   = 2'b00;
    localparam logic [1:0] SLVERR = 2'b10;

    // ---- write channel ------------------------------------------------------------------------------------------------------------------
    logic        rst, aw_got, w_got, do_wr;
    logic [3:0]  awa;
    // verilator lint_off UNUSEDSIGNAL
    logic [31:0] wd;                                 // bits above WH are not used
    // verilator lint_on UNUSEDSIGNAL
    logic [3:0]  s_axil_wstrb_q;
    logic        full_strb;
    logic        dropped, sat;
    logic [LOGN-1:0] caddr;
    logic signed [WH-1:0] st_re, st_im;
    always_comb begin
        rst            = ~aresetn;
        s_axil_awready = !aw_got && !s_axil_bvalid;
        s_axil_wready  = !w_got && !s_axil_bvalid;
        do_wr          = aw_got && w_got && !s_axil_bvalid;
        full_strb      = (s_axil_wstrb_q == 4'hF);
        coef_we        = do_wr && full_strb && (awa == 4'd7) && !busy;
        coef_addr      = caddr;
        coef_re        = st_re;
        coef_im        = WH'(wd);
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            aw_got        <= 1'b0;
            w_got         <= 1'b0;
            s_axil_bvalid <= 1'b0;
            s_axil_bresp  <= OKAY;
            dropped       <= 1'b0;
            sat           <= 1'b0;
            caddr         <= '0;
        end else begin
            if (sat_pulse) sat <= 1'b1;
            if (s_axil_bvalid && s_axil_bready) s_axil_bvalid <= 1'b0;
            if (s_axil_awvalid && s_axil_awready) aw_got <= 1'b1;
            if (s_axil_wvalid && s_axil_wready) w_got <= 1'b1;
            if (do_wr) begin
                aw_got        <= 1'b0;
                w_got         <= 1'b0;
                s_axil_bvalid <= 1'b1;
                s_axil_bresp  <= SLVERR;
                if (full_strb) begin
                    case (awa)
                        4'd3: begin                                  // STATUS: write 1 to clear DROPPED, SAT
                            s_axil_bresp <= OKAY;
                            if (wd[1]) dropped <= 1'b0;
                            if (wd[2] && !sat_pulse) sat <= 1'b0;
                        end
                        4'd5: begin
                            s_axil_bresp <= OKAY;
                            caddr        <= wd[LOGN-1:0];
                        end
                        4'd6: s_axil_bresp <= OKAY;
                        4'd7: begin
                            if (busy) dropped <= 1'b1;
                            else begin
                                s_axil_bresp <= OKAY;
                                caddr        <= caddr + 1'b1;
                            end
                        end
                        default: ;
                    endcase
                end
            end
        end
    end
    always_ff @(posedge clk) begin
        if (s_axil_awvalid && s_axil_awready) awa <= s_axil_awaddr[5:2];
        if (s_axil_wvalid && s_axil_wready) begin
            wd             <= s_axil_wdata;
            s_axil_wstrb_q <= s_axil_wstrb;
        end
        if (do_wr && full_strb && awa == 4'd6) st_re <= WH'(wd);
        if (do_wr && full_strb && awa == 4'd7) st_im <= WH'(wd);
    end

    // ---- read channel -------------------------------------------------------------------------------------------------------------------
    logic [31:0] rd_val;
    logic        rd_ok;
    always_comb begin
        rd_val = '0;
        rd_ok  = 1'b1;
        case (s_axil_araddr[5:2])
            4'd0:    rd_val = 32'h46435631;
            4'd1:    rd_val = {16'(L), 8'(W), 3'd0, 5'(LOGN)};
            4'd2:    rd_val = {12'd0, 4'(GB), 8'(FH), 8'(WH)};
            4'd3:    rd_val = {29'd0, sat, dropped, busy};
            4'd4:    rd_val = blocks;
            4'd5:    rd_val = 32'(caddr);
            4'd6:    rd_val = 32'(st_re);
            4'd7:    rd_val = 32'(st_im);
            default: rd_ok = 1'b0;
        endcase
    end
    assign s_axil_arready = !s_axil_rvalid;
    always_ff @(posedge clk) begin
        if (rst) begin
            s_axil_rvalid <= 1'b0;
            s_axil_rdata  <= '0;
            s_axil_rresp  <= OKAY;
        end else begin
            if (s_axil_rvalid && s_axil_rready) s_axil_rvalid <= 1'b0;
            if (s_axil_arvalid && s_axil_arready) begin
                s_axil_rvalid <= 1'b1;
                s_axil_rdata  <= rd_val;
                s_axil_rresp  <= rd_ok ? OKAY : SLVERR;
            end
        end
    end
endmodule
