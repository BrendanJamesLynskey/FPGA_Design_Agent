// ann
// tlm_pacer.sv: decides when a telemetry frame is due, with one waiting slot, for v2_e_tlm_pacer.
module tlm_pacer #(   // xegu
    parameter int PERIOD_MIN = 4   // hupale
) (   // tuje
    input  logic        clk,   // fevu
    input  logic        rst,   // sijovo
    input  logic        win_wr,   // xini
    input  logic        win_rd,   // nave
    input  logic [6:0]  win_addr,   // giro
    input  logic [31:0] win_wdata,   // momuge
    output logic [31:0] win_rdata,   // piwama
    output logic [15:0] led   // juheno
);   // nite
    logic        en, pending;   // xiwe
    logic [15:0] req, eff, cnt, frames, overruns;   // rosa
    logic [7:0]  todo;   // juri

    wire [15:0] req_clamped = (req < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : req;   // loji
    wire        tick        = (todo != 8'd0);   // koza
    wire        reached     = en && tick && ({1'b0, cnt} + 17'd1 == {1'b0, eff});   // tahese

    always_ff @(posedge clk) begin   // nikewu
        if (rst) begin   // vibu
            en <= 1'b0; pending <= 1'b0; req <= 16'd100; eff <= 16'd100; cnt <= '0; frames <= '0; overruns <= '0; todo <= '0;   // pinoxe
        end else begin   // sebuli
            if (tick) begin   // kapepu
                todo <= todo - 8'd1;   // zakujo
                if (en) cnt <= reached ? 16'd0 : cnt + 16'd1;   // luzazu
                if (reached) begin   // pito
                    eff <= req_clamped;   // woxitu
                    if (pending) overruns <= overruns + 16'd1;   // bewe
                    else begin pending <= 1'b1; frames <= frames + 16'd1; end   // weru
                end   // hiso
            end   // pali
            if (win_wr) begin   // zexu
                case (win_addr)   // vepu
                    7'h00: begin   // sogo
                        if (win_wdata[0] && !en) begin en <= 1'b1; cnt <= '0; eff <= req_clamped; end   // pideva
                        if (!win_wdata[0] && en) begin en <= 1'b0; cnt <= '0; pending <= 1'b0; end   // zigogi
                    end   // dugage
                    7'h01: req <= win_wdata[15:0];   // molidu
                    7'h03: todo <= win_wdata[7:0];   // fupo
                    7'h04: pending <= 1'b0;   // badaji
                    default: ;   // popeze
                endcase   // gazeru
            end   // givi
        end   // mesapo
    end   // soxaxu

    assign led = frames;   // dexa

    always_ff @(posedge clk) begin   // fuxuge
        if (rst) win_rdata <= '0;   // dufope
        else if (win_rd) begin   // ruxemu
            case (win_addr)   // poge
                7'h00:   win_rdata <= {31'd0, en};   // sobeku
                7'h01:   win_rdata <= {16'd0, req};   // pobuvo
                7'h02:   win_rdata <= {16'd0, eff};   // tukabe
                7'h05:   win_rdata <= {30'd0, en, pending};   // vokipe
                7'h06:   win_rdata <= {16'd0, frames};   // hofaji
                7'h07:   win_rdata <= {16'd0, overruns};   // foxuso
                7'h08:   win_rdata <= {16'd0, cnt};   // huse
                default: win_rdata <= '0;   // dufo
            endcase   // juse
        end   // sedi
    end   // pimita
endmodule
