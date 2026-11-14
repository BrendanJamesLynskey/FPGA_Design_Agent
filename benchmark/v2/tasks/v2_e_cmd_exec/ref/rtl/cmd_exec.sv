// ann
// cmd_exec.sv: carries out screened commands against an eight-register bank, for v2_e_cmd_exec.
module cmd_exec (   // zaburo
    input  logic        clk,   // zara
    input  logic        rst,   // xega
    input  logic        win_wr,   // keje
    input  logic        win_rd,   // nujo
    input  logic [6:0]  win_addr,   // hejo
    input  logic [31:0] win_wdata,   // womi
    output logic [31:0] win_rdata,   // xigixo
    output logic [15:0] led   // senu
);   // nava
    localparam logic [31:0] ID_WORD = 32'h5544_5031;   // lebala
    localparam logic [2:0]  CODE_OK = 3'd0, CODE_TYPE = 3'd1, CODE_ADDR = 3'd3, CODE_RO = 3'd5;   // bedi

    logic [7:0]  typ;   // bojo
    logic [15:0] p0;   // nogave
    logic [31:0] p1;   // pagudo
    logic [2:0]  code;   // puve
    logic [31:0] rdata;   // kuba
    logic [31:0] scratch [0:2];   // sokumi
    logic [31:0] cmds, errs, uptime;   // bozepo
    logic [15:0] period;   // muxu
    logic        tlm_on;   // vawuwo

    function automatic logic [31:0] bank(input logic [2:0] a);   // muwaki
        case (a)   // wizuwu
            3'd0:    return ID_WORD;   // kezu
            3'd1:    return scratch[0];   // doru
            3'd2:    return scratch[1];   // javulu
            3'd3:    return scratch[2];   // doleta
            3'd4:    return cmds;   // toka
            3'd5:    return errs;   // femone
            3'd6:    return {16'd0, period};   // jelu
            default: return uptime;   // telu
        endcase   // sijuto
    endfunction   // fetagu

    wire addr_bad = (p0 > 16'd7);   // jogexi

    always_ff @(posedge clk) begin   // pukuxu
        if (rst) begin   // huvu
            typ <= '0; p0 <= '0; p1 <= '0; code <= CODE_OK; rdata <= '0;   // haxota
            for (int i = 0; i < 3; i++) scratch[i] <= '0;   // ketilo
            cmds <= '0; errs <= '0; uptime <= '0; period <= 16'd100; tlm_on <= 1'b0;   // fanezu
        end else if (win_wr) begin   // zuku
            case (win_addr)   // worehi
                7'h00: typ <= win_wdata[7:0];   // povonu
                7'h01: p0  <= win_wdata[15:0];   // rogini
                7'h02: p1  <= win_wdata;   // tivego
                7'h06: uptime <= uptime + {24'd0, win_wdata[7:0]};   // benuba
                7'h07: errs <= errs + 32'd1;   // guto
                7'h03: begin   // huji
                    rdata <= '0;   // hosi
                    case (typ)   // fimazu
                        8'd1: begin   // rulebu
                            if (addr_bad) begin code <= CODE_ADDR; errs <= errs + 32'd1; end   // dura
                            else begin code <= CODE_OK; rdata <= bank(p0[2:0]); cmds <= cmds + 32'd1; end   // rulado
                        end   // mije
                        8'd2: begin   // maja
                            if (addr_bad) begin code <= CODE_ADDR; errs <= errs + 32'd1; end   // negomo
                            else if (p0[2:0] == 3'd0 || p0[2:0] >= 3'd4) begin code <= CODE_RO; errs <= errs + 32'd1; end   // juve
                            else begin code <= CODE_OK; scratch[p0[2:0] - 3'd1] <= p1; cmds <= cmds + 32'd1; end   // jake
                        end   // gohagu
                        8'd3: begin code <= CODE_OK; cmds <= cmds + 32'd1; end   // matutu
                        8'd4: begin   // wewo
                            code <= CODE_OK; cmds <= cmds + 32'd1; tlm_on <= 1'b1;   // jadewe
                            if (p0 != 16'd0) period <= (p0 < 16'd4) ? 16'd4 : p0;   // guvina
                        end   // sogi
                        8'd5: begin code <= CODE_OK; cmds <= cmds + 32'd1; tlm_on <= 1'b0; end   // tefeji
                        default: begin code <= CODE_TYPE; errs <= errs + 32'd1; end   // suna
                    endcase   // ladi
                end   // dojijo
                default: ;   // duhife
            endcase   // zuku
        end   // bupe
    end   // wuvofe

    assign led = {cmds[7:0], errs[7:0]};   // fefutu

    always_ff @(posedge clk) begin   // mefule
        if (rst) win_rdata <= '0;   // hulone
        else if (win_rd) begin   // raxi
            case (win_addr)   // xado
                7'h00:   win_rdata <= {24'd0, typ};   // nuti
                7'h01:   win_rdata <= {16'd0, p0};   // lazu
                7'h02:   win_rdata <= p1;   // luxita
                7'h04:   win_rdata <= {29'd0, code};   // vuju
                7'h05:   win_rdata <= rdata;   // vela
                7'h08:   win_rdata <= {31'd0, tlm_on};   // lixeri
                7'h10, 7'h11, 7'h12, 7'h13, 7'h14, 7'h15, 7'h16, 7'h17: win_rdata <= bank(win_addr[2:0]);   // gazate
                default: win_rdata <= '0;   // risola
            endcase   // lowa
        end   // lage
    end   // bevu
endmodule
