// cps_regs: window register decode, seven 16-bit class counters, last-good-packet fields, LEDs.
module cps_regs (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,    // only bits [8:0] are used (BYTE register)
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    // to the core
    output logic        byte_vld,
    output logic [7:0]  byte_data,
    output logic        byte_end,
    // from the core
    input  logic        busy,
    input  logic        done,
    input  logic [3:0]  cls,
    input  logic [7:0]  g_type,
    input  logic [15:0] g_seq,
    input  logic [15:0] g_pay0,
    input  logic [31:0] g_pay1,
    input  logic [15:0] last_seq,
    input  logic        have_seq,
    output logic [15:0] led
);
    logic [8:0]  byte_reg;
    logic [15:0] ctr_good, ctr_crc, ctr_short, ctr_long, ctr_repeat, ctr_stale, ctr_proto;
    logic [3:0]  result;
    logic [7:0]  r_type;
    logic [15:0] r_seq, r_pay0;
    logic [31:0] r_pay1;

    always_ff @(posedge clk) begin
        byte_vld <= 1'b0;
        if (rst) begin
            byte_reg   <= 9'h0;
            byte_data  <= 8'h0;
            byte_end   <= 1'b0;
            ctr_good   <= 16'h0;
            ctr_crc    <= 16'h0;
            ctr_short  <= 16'h0;
            ctr_long   <= 16'h0;
            ctr_repeat <= 16'h0;
            ctr_stale  <= 16'h0;
            ctr_proto  <= 16'h0;
            result     <= 4'h0;
            r_type     <= 8'h0;
            r_seq      <= 16'h0;
            r_pay0     <= 16'h0;
            r_pay1     <= 32'h0;
            win_rdata  <= 32'h0;
            led        <= 16'h0;
        end else begin
            if (win_wr && win_addr == 7'h00) begin
                byte_reg  <= win_wdata[8:0];
                byte_data <= win_wdata[7:0];
                byte_end  <= win_wdata[8];
                byte_vld  <= 1'b1;
            end
            if (done) begin
                result <= cls;
                case (cls)
                    4'd1: begin
                        ctr_good <= ctr_good + 16'd1;
                        r_type   <= g_type;
                        r_seq    <= g_seq;
                        r_pay0   <= g_pay0;
                        r_pay1   <= g_pay1;
                    end
                    4'd2: ctr_crc    <= ctr_crc + 16'd1;
                    4'd3: ctr_short  <= ctr_short + 16'd1;
                    4'd4: ctr_long   <= ctr_long + 16'd1;
                    4'd5: ctr_repeat <= ctr_repeat + 16'd1;
                    4'd6: ctr_stale  <= ctr_stale + 16'd1;
                    4'd7, 4'd8: ctr_proto <= ctr_proto + 16'd1;
                    default: ;
                endcase
            end
            led <= {last_seq[7:0], ctr_good[7:0]};
            if (win_rd) begin
                case (win_addr)
                    7'h00: win_rdata <= {23'h0, byte_reg};
                    7'h01: win_rdata <= {28'h0, result};
                    7'h02: win_rdata <= {24'h0, r_type};
                    7'h03: win_rdata <= {16'h0, r_seq};
                    7'h04: win_rdata <= {16'h0, r_pay0};
                    7'h05: win_rdata <= r_pay1;
                    7'h06: win_rdata <= {15'h0, have_seq, last_seq};
                    7'h07: win_rdata <= {31'h0, busy};
                    7'h10: win_rdata <= {16'h0, ctr_good};
                    7'h11: win_rdata <= {16'h0, ctr_crc};
                    7'h12: win_rdata <= {16'h0, ctr_short};
                    7'h13: win_rdata <= {16'h0, ctr_long};
                    7'h14: win_rdata <= {16'h0, ctr_repeat};
                    7'h15: win_rdata <= {16'h0, ctr_stale};
                    7'h16: win_rdata <= {16'h0, ctr_proto};
                    default: win_rdata <= 32'h0;
                endcase
            end
        end
    end
endmodule
