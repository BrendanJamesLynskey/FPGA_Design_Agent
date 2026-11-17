// Reply frame builder with CRC-32, behind the test shell register window.
module v2_e_resp_builder_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    // reset: 2-FF synchroniser on the button, inverted once to active high
    (* ASYNC_REG = "TRUE" *) logic [1:0] rst_sync;
    logic rst;
    always_ff @(posedge CLK100MHZ) rst_sync <= {rst_sync[0], CPU_RESETN};
    assign rst = ~rst_sync[1];

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [15:0] win_wdata_hi_unused;
    /* verilator lint_on UNUSEDSIGNAL */
    assign win_wdata_hi_unused = win_wdata[31:16];

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h52534231), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    logic [6:0]  r_type;
    logic [7:0]  r_status;
    logic [15:0] r_seq;
    logic [6:0]  r_idx;
    logic [4:0]  pcnt;
    logic        ovf, building;
    logic [5:0]  rlen;
    logic [7:0]  rstat;

    logic [7:0] pay_mem [0:31];
    logic [7:0] rep_mem [0:63];

    // build snapshot and engine
    logic [6:0]  s_type;
    logic [7:0]  s_status;
    logic [15:0] s_seq;
    logic [5:0]  pos;
    logic [31:0] crc;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++)
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    wire wr_ok_pl = win_wr && (win_addr == 7'd3) && !building;
    wire wr_build = win_wr && (win_addr == 7'd4) && !building;

    logic [5:0] last_pos;
    assign last_pos = 6'd8 + {1'b0, pcnt};

    logic [4:0] pay_ra;
    assign pay_ra = 5'(pos - 6'd5);
    logic [7:0] pay_rd;
    assign pay_rd = pay_mem[pay_ra];
    logic [31:0] crc_fin;
    assign crc_fin = ~crc;

    logic [7:0] bld_byte;
    always_comb begin
        if (pos == 6'd0)       bld_byte = {1'b1, s_type};
        else if (pos == 6'd1)  bld_byte = s_status;
        else if (pos == 6'd2)  bld_byte = s_seq[15:8];
        else if (pos == 6'd3)  bld_byte = s_seq[7:0];
        else if (pos == 6'd4)  bld_byte = {3'b0, pcnt};
        else if (pos < 6'd5 + {1'b0, pcnt}) bld_byte = pay_rd;
        else begin
            case (pos - (6'd5 + {1'b0, pcnt}))
                6'd0: bld_byte = crc_fin[7:0];
                6'd1: bld_byte = crc_fin[15:8];
                6'd2: bld_byte = crc_fin[23:16];
                default: bld_byte = crc_fin[31:24];
            endcase
        end
    end
    wire is_crc_byte = (pos >= 6'd5 + {1'b0, pcnt});

    always_ff @(posedge CLK100MHZ) begin
        if (wr_ok_pl && pcnt < 5'd24) pay_mem[pcnt] <= win_wdata[7:0];
        if (building) rep_mem[pos] <= bld_byte;
    end

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            r_type <= '0; r_status <= '0; r_seq <= '0; r_idx <= '0;
            pcnt <= '0; ovf <= 1'b0; building <= 1'b0;
            rlen <= '0; rstat <= '0; pos <= '0;
        end else begin
            if (win_wr) begin
                case (win_addr)
                    7'd0: r_type   <= win_wdata[6:0];
                    7'd1: r_status <= win_wdata[7:0];
                    7'd2: r_seq    <= win_wdata[15:0];
                    7'd5: r_idx    <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (wr_ok_pl) begin
                if (pcnt < 5'd24) pcnt <= pcnt + 5'd1;
                else ovf <= 1'b1;
            end
            if (wr_build) begin
                building <= 1'b1;
                pos      <= '0;
            end
            if (building) begin
                pos <= pos + 6'd1;
                if (pos == last_pos) begin
                    building <= 1'b0;
                    rlen  <= 6'd9 + {1'b0, pcnt};
                    rstat <= s_status;
                    pcnt  <= '0;
                    ovf   <= 1'b0;
                end
            end
        end
    end

    // datapath registers (no reset): snapshot and CRC
    always_ff @(posedge CLK100MHZ) begin
        if (wr_build) begin
            s_type <= r_type; s_status <= r_status; s_seq <= r_seq;
            crc <= 32'hFFFFFFFF;
        end else if (building && !is_crc_byte) begin
            crc <= crc8(crc, bld_byte);
        end
    end

    logic [7:0] byte_rd;
    assign byte_rd = ({1'b0, r_idx} < {2'b0, rlen}) ? rep_mem[r_idx[5:0]] : 8'h00;

    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'd0: win_rdata <= {25'h0, r_type};
                7'd1: win_rdata <= {24'h0, r_status};
                7'd2: win_rdata <= {16'h0, r_seq};
                7'd5: win_rdata <= {25'h0, r_idx};
                7'd6: win_rdata <= {24'h0, byte_rd};
                7'd7: win_rdata <= {26'h0, rlen};
                7'd8: win_rdata <= {30'h0, ovf, building};
                7'd9: win_rdata <= {27'h0, pcnt};
                default: win_rdata <= '0;
            endcase
        end
    end

    assign LED = {rstat, 2'b00, rlen};
endmodule
