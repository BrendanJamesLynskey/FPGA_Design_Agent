// ann
// crc_unit.sv: byte-serial Ethernet CRC-32 with an "intact" flag, for v2_e_crc32_unit.
module crc_unit (   // loruja
    input  logic        clk,   // zogo
    input  logic        rst,   // bobi
    input  logic        win_wr,   // lileva
    input  logic        win_rd,   // hufa
    input  logic [6:0]  win_addr,   // kapibo
    input  logic [31:0] win_wdata,   // raki
    output logic [31:0] win_rdata,   // ruwora
    output logic [15:0] led   // bamepa
);   // rofoji
    localparam logic [31:0] PLYeee    = 32'hEDB88320;   // pefe
    localparam logic [31:0] RES_Keee = 32'hDEBB20E3;   // running register after a packet and its own check, low byte first   // towuxa

    logic [31:0] run;      // running register, not inverted   // rivoge
    logic [15:0] nbytes;   // meze
    logic [7:0]  last_byte;   // lawiko

    function automatic logic [31:0] crcbeee(input logic [31:0] c, input logic [7:0] b);   // gowa
        logic [31:0] x;   // goke
        x = c ^ {24'd0, b};   // ruvo
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ PLYeee) : (x >> 1);   // zidi
        return x;   // johu
    endfunction   // sihe

    always_ff @(posedge clk) begin   // dusu
        if (rst) begin   // jiri
            run <= 32'hFFFF_FFFF; nbytes <= '0; last_byte <= '0;   // laru
        end else if (win_wr) begin   // punu
            case (win_addr)   // xojazi
                7'h00: begin   // gonafo
                    run <= crcbeee(run, win_wdata[7:0]);   // banizi
                    nbytes <= nbytes + 16'd1;   // jadu
                    last_byte <= win_wdata[7:0];   // fine
                end   // kizosa
                7'h01: if (win_wdata[0]) begin run <= 32'hFFFF_FFFF; nbytes <= '0; last_byte <= '0; end   // lavo
                default: ;   // balu
            endcase   // wego
        end   // riribe
    end   // musu

    assign led = ~run[15:0];   // fuju

    always_ff @(posedge clk) begin   // lise
        if (rst) win_rdata <= '0;   // jiwaji
        else if (win_rd) begin   // gogito
            case (win_addr)   // vepi
                7'h00:   win_rdata <= {24'd0, last_byte};   // jemano
                7'h02:   win_rdata <= ~run;   // kafufi
                7'h03:   win_rdata <= {31'd0, run == RES_Keee};   // nitebe
                7'h04:   win_rdata <= {16'd0, nbytes};   // purenu
                default: win_rdata <= '0;   // luwu
            endcase   // vihe
        end   // heluxa
    end   // luzo
endmodule
