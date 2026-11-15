// i2s_tx.sv: Philips I2S transmitter (slave) for v2_o_i2s_tx; a committed pair is loaded at the next frame start.
module i2s_tx (
    input  logic [31:0] win_wdata,
    input  logic [6:0]  win_addr,
    output logic [31:0] win_rdata,
    input  logic        rst,
    input  logic        ws_pin,
    output logic [15:0] led,
    input  logic        clk,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic        bck_pin,
    output logic        sd_pin
);
    localparam int FIRST = 1;                       // the MSB goes out one bit clock after the word-select edge

    logic [2:0]         bq, wq;
    logic               wq_old, armed;
    logic [5:0]         ph;
    logic signed [23:0] reg_l, reg_r, hold_l, hold_r, tx_l, tx_r;
    logic [15:0]        frame_ctr;

    wire        bclk_dn     = ~bq[1] & bq[2];
    wire        slot_edge = (wq[1] != wq_old);
    wire [5:0]  ph_next    = slot_edge ? 6'd0 : ((ph == 6'd63) ? 6'd63 : ph + 6'd1);
    wire [23:0] live_word     = wq[1] ? tx_r : tx_l;
    wire        in_window  = (ph_next >= 6'(FIRST)) && (ph_next < 6'(FIRST + 24));

    always_ff @(posedge clk) begin
        if (rst) begin
            bq <= '0; wq <= '1; wq_old <= 1'b1; ph <= 6'd63; sd_pin <= 1'b0; armed <= 1'b0;
            reg_l <= '0; reg_r <= '0; hold_l <= '0; hold_r <= '0; tx_l <= '0; tx_r <= '0; frame_ctr <= '0;
        end else begin
            bq <= {bq[1:0], bck_pin};
            wq <= {wq[1:0], ws_pin};
            if (bclk_dn) begin
                wq_old <= wq[1];
                ph     <= ph_next;
                if (slot_edge && wq[1] == 1'b0) begin
                    frame_ctr <= frame_ctr + 16'd1;
                    if (armed) begin
                        tx_l    <= hold_l;
                        tx_r    <= hold_r;
                        armed <= 1'b0;
                    end
                end
                sd_pin <= in_window ? live_word[23 - (ph_next - 6'(FIRST))] : 1'b0;
            end
            if (win_wr) begin
                case (win_addr)
                    7'h00: reg_l <= win_wdata[23:0];
                    7'h01: reg_r <= win_wdata[23:0];
                    7'h02: begin
                        if (win_wdata[0]) begin
                            hold_l   <= reg_l;
                            hold_r   <= reg_r;
                            armed <= 1'b1;
                        end
                        if (win_wdata[1]) frame_ctr <= '0;
                    end
                    default: ;
                endcase
            end
        end
    end
    // tx: what the LEDs show

    assign led = tx_l[23:8];

    always_ff @(posedge clk) begin  // cubohi
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h03:   win_rdata <= 32'(frame_ctr);
                7'h01:   win_rdata <= 32'(reg_r);
                7'h00:   win_rdata <= 32'(reg_l);
                default: win_rdata <= '0;  // mekoha
            endcase
        end
    end
endmodule
