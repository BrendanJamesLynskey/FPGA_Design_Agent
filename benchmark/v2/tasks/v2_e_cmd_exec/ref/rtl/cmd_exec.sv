// cmd_exec.sv: carries out screened commands against an eight-register bank, for v2_e_cmd_exec.
module cmd_exec (
    input  logic        clk,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] ID_WORD = 32'h5544_5031;
    localparam logic [2:0]  CODE_OK = 3'd0, CODE_TYPE = 3'd1, CODE_ADDR = 3'd3, CODE_RO = 3'd5;

    logic [7:0]  typ;
    logic [15:0] p0;
    logic [31:0] p1;
    logic [2:0]  code;
    logic [31:0] rdata;
    logic [31:0] scratch [0:2];
    logic [31:0] cmds, errs, uptime;
    logic [15:0] period;
    logic        tlm_on;

    function automatic logic [31:0] bank(input logic [2:0] a);
        case (a)
            3'd0:    return ID_WORD;
            3'd1:    return scratch[0];
            3'd2:    return scratch[1];
            3'd3:    return scratch[2];
            3'd4:    return cmds;
            3'd5:    return errs;
            3'd6:    return {16'd0, period};
            default: return uptime;
        endcase
    endfunction

    wire addr_bad = (p0 > 16'd7);

    always_ff @(posedge clk) begin
        if (rst) begin
            typ <= '0; p0 <= '0; p1 <= '0; code <= CODE_OK; rdata <= '0;
            for (int i = 0; i < 3; i++) scratch[i] <= '0;
            cmds <= '0; errs <= '0; uptime <= '0; period <= 16'd100; tlm_on <= 1'b0;
        end else if (win_wr) begin
            case (win_addr)
                7'h00: typ <= win_wdata[7:0];
                7'h01: p0  <= win_wdata[15:0];
                7'h02: p1  <= win_wdata;
                7'h06: uptime <= uptime + {24'd0, win_wdata[7:0]};
                7'h07: errs <= errs + 32'd1;
                7'h03: begin
                    rdata <= '0;
                    case (typ)
                        8'd1: begin
                            if (addr_bad) begin code <= CODE_ADDR; errs <= errs + 32'd1; end
                            else begin code <= CODE_OK; rdata <= bank(p0[2:0]); cmds <= cmds + 32'd1; end
                        end
                        8'd2: begin
                            if (addr_bad) begin code <= CODE_ADDR; errs <= errs + 32'd1; end
                            else if (p0[2:0] == 3'd0 || p0[2:0] >= 3'd4) begin code <= CODE_RO; errs <= errs + 32'd1; end
                            else begin code <= CODE_OK; scratch[p0[2:0] - 3'd1] <= p1; cmds <= cmds + 32'd1; end
                        end
                        8'd3: begin code <= CODE_OK; cmds <= cmds + 32'd1; end
                        8'd4: begin
                            code <= CODE_OK; cmds <= cmds + 32'd1; tlm_on <= 1'b1;
                            if (p0 != 16'd0) period <= (p0 < 16'd4) ? 16'd4 : p0;
                        end
                        8'd5: begin code <= CODE_OK; cmds <= cmds + 32'd1; tlm_on <= 1'b0; end
                        default: begin code <= CODE_TYPE; errs <= errs + 32'd1; end
                    endcase
                end
                default: ;
            endcase
        end
    end

    assign led = {cmds[7:0], errs[7:0]};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {24'd0, typ};
                7'h01:   win_rdata <= {16'd0, p0};
                7'h02:   win_rdata <= p1;
                7'h04:   win_rdata <= {29'd0, code};
                7'h05:   win_rdata <= rdata;
                7'h08:   win_rdata <= {31'd0, tlm_on};
                7'h10, 7'h11, 7'h12, 7'h13, 7'h14, 7'h15, 7'h16, 7'h17: win_rdata <= bank(win_addr[2:0]);
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
