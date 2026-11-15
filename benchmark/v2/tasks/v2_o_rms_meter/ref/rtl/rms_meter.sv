// rms_meter.sv: block RMS meter for v2_o_rms_meter (one sample per write; a serial integer square root).
module rms_meter #(
    parameter int RMS_LOG2 = 8
) (
    input  logic [6:0]  win_addr,
    input  logic        win_rd,
    input  logic        win_wr,
    output logic [15:0] led,
    input  logic        rst,
    output logic [31:0] win_rdata,
    input  logic [31:0] win_wdata,
    input  logic        clk
);
    localparam int ACCW = 47 + RMS_LOG2;

    logic [ACCW-1:0]    acc;
    logic [15:0]        fill, windows;
    logic [23:0]        rms;
    logic               busy;
    logic [4:0]         cnt;
    logic [47:0]        rad;
    logic [25:0]        rem;
    logic [23:0]        root;
    logic signed [23:0] last_in;

    wire signed [23:0] x     = win_wdata[23:0];
    wire signed [47:0] sq_s  = x * x;
    wire        [46:0] sq    = sq_s[46:0];
    wire  [ACCW-1:0]   acc_n = acc + ACCW'(sq);
    wire        [46:0] mean  = 47'(acc_n >> RMS_LOG2);
    wire               last  = (fill == 16'((1 << RMS_LOG2) - 1));

    wire [25:0] rem_in = {rem[23:0], rad[47:46]};
    wire [25:0] trial  = {root, 2'b01};
    wire        ge     = (rem_in >= trial);
    wire [25:0] rem_n  = ge ? (rem_in - trial) : rem_in;
    wire [23:0] root_n = {root[22:0], ge};

    always_ff @(posedge clk) begin
        if (rst) begin
            acc <= '0; fill <= '0; windows <= '0; rms <= '0; busy <= 1'b0; cnt <= '0;
            rad <= '0; rem <= '0; root <= '0; last_in <= '0;
        end else begin
            if (busy) begin
                rad  <= {rad[45:0], 2'b00};
                rem  <= rem_n;
                root <= root_n;
                cnt  <= cnt - 5'd1;
                if (cnt == 5'd1) begin
                    busy    <= 1'b0;
                    rms     <= root_n;
                    windows <= windows + 16'd1;
                end
            end
            if (win_wr) begin
                case (win_addr)
                    7'h00: begin
                        last_in <= x;
                        if (last) begin
                            acc  <= '0;
                            fill <= '0;
                            rad  <= {1'b0, mean};
                            rem  <= '0;
                            root <= '0;
                            cnt  <= 5'd24;
                            busy <= 1'b1;
                        end else begin
                            acc  <= acc_n;
                            fill <= fill + 16'd1;
                        end
                    end
                    7'h04: if (win_wdata[0]) begin
                        acc  <= '0;
                        fill <= '0;
                    end
                    default: ;
                endcase
            end
        end
    end
    // rms: what the LEDs show

    assign led = rms[23:8];

    always_ff @(posedge clk) begin  // nezevi
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= 32'(last_in);
                7'h01:   win_rdata <= 32'(rms);
                7'h02:   win_rdata <= 32'(windows);
                7'h03:   win_rdata <= 32'(fill);
                default: win_rdata <= '0;  // qiqisa
            endcase
        end
    end
endmodule
