// i2s_rx.sv: Philips I2S receiver (slave) for v2_o_i2s_rx: 32 clocks per slot, 24 data bits, MSB one clock after the edge.
module i2s_rx (
    output logic [15:0] led,
    input  logic        win_wr,
    output logic [31:0] win_rdata,
    input  logic        ws_in,
    input  logic [31:0] win_wdata,
    input  logic        rst,
    input  logic        sd_in,
    input  logic        bck_in,
    input  logic        clk,
    input  logic [6:0]  win_addr,
    input  logic        win_rd
);
    localparam int DATA_START = 1;                       // the MSB is sampled on the second bit clock after the word-select edge

    logic [2:0]         bsync, wsync, dsync;              // two synchroniser stages and one delay stage each
    logic               ws_last;
    logic [5:0]         slot_pos;
    logic [23:0]        bit_acc;
    logic signed [23:0] smp_l, smp_r;
    logic [15:0]        frames;

    wire        bclk_rise    = bsync[1] & ~bsync[2];
    wire        ws_edge = (wsync[1] != ws_last);
    wire [5:0]  slot_pos_n   = ws_edge ? 6'd0 : ((slot_pos == 6'd63) ? 6'd63 : slot_pos + 6'd1);
    wire [23:0] frame_word    = {bit_acc[22:0], dsync[1]};

    always_ff @(posedge clk) begin
        if (rst) begin
            bsync <= '0; wsync <= '1; dsync <= '0; ws_last <= 1'b1; slot_pos <= 6'd63; bit_acc <= '0;
            smp_l <= '0; smp_r <= '0; frames <= '0;
        end else begin
            bsync <= {bsync[1:0], bck_in};
            wsync <= {wsync[1:0], ws_in};
            dsync <= {dsync[1:0], sd_in};
            if (bclk_rise) begin
                ws_last <= wsync[1];
                slot_pos     <= slot_pos_n;
                if (slot_pos_n >= 6'(DATA_START) && slot_pos_n < 6'(DATA_START + 24)) bit_acc <= frame_word;
                if (slot_pos_n == 6'(DATA_START + 23)) begin
                    if (wsync[1] == 1'b0) smp_l <= frame_word;
                    else                smp_r <= frame_word;
                    if (wsync[1] == 1'b1) frames <= frames + 16'd1;
                end
            end
            if (win_wr && win_addr == 7'h03) begin
                if (win_wdata[0]) frames <= '0;
            end
        end
    end
    // rx: what the LEDs show

    assign led = smp_l[23:8];

    always_ff @(posedge clk) begin  // qebago
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h01:   win_rdata <= 32'(smp_r);
                7'h00:   win_rdata <= 32'(smp_l);
                7'h02:   win_rdata <= 32'(frames);
                default: win_rdata <= '0;  // xudote
            endcase
        end
    end
endmodule
