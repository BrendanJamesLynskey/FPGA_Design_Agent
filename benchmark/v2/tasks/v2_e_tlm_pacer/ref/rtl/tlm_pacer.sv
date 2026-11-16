// tlm_pacer.sv: decides when a telemetry frame is due, with one waiting slot, for v2_e_tlm_pacer.
module tlm_pacer #(
    parameter int PERIOD_MIN = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [6:0]  win_addr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    logic        en, pending;
    logic [15:0] req, eff, cnt, frames, overruns;
    logic [7:0]  todo;

    wire [15:0] req_clamped = (req < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : req;
    wire        tick        = (todo != 8'd0);
    wire        reached     = en && tick && ({1'b0, cnt} + 17'd1 == {1'b0, eff});

    always_ff @(posedge clk) begin
        if (rst) begin
            en <= 1'b0; pending <= 1'b0; req <= 16'd100; eff <= 16'd100; cnt <= '0; frames <= '0; overruns <= '0; todo <= '0;
        end else begin
            if (tick) begin
                todo <= todo - 8'd1;
                if (en) cnt <= reached ? 16'd0 : cnt + 16'd1;
                if (reached) begin
                    eff <= req_clamped;
                    if (pending) overruns <= overruns + 16'd1;
                    else begin pending <= 1'b1; frames <= frames + 16'd1; end
                end
            end
            if (win_wr) begin
                case (win_addr)
                    7'h00: begin
                        if (win_wdata[0] && !en) begin en <= 1'b1; cnt <= '0; eff <= req_clamped; end
                        if (!win_wdata[0] && en) begin en <= 1'b0; cnt <= '0; pending <= 1'b0; end
                    end
                    7'h01: req <= win_wdata[15:0];
                    7'h03: todo <= win_wdata[7:0];
                    7'h04: pending <= 1'b0;
                    default: ;
                endcase
            end
        end
    end

    assign led = frames;

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {31'd0, en};
                7'h01:   win_rdata <= {16'd0, req};
                7'h02:   win_rdata <= {16'd0, eff};
                7'h05:   win_rdata <= {30'd0, en, pending};
                7'h06:   win_rdata <= {16'd0, frames};
                7'h07:   win_rdata <= {16'd0, overruns};
                7'h08:   win_rdata <= {16'd0, cnt};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
