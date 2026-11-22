// tb_stream: generic stream harness for the arithmetic library (brief 139b). One input vector per accepted in_valid/in_ready beat; every
// output beat is compared with the next expected word; the latency (clock edges from the accepting edge to the edge that samples out_valid)
// of every result is compared with LAT. The DUT is a <function>_sel wrapper connected by the function's own tb_<function>.sv.
// Vectors come from model.py as hex files: +vin=<file> +vexp=<file>. The result line is parsed by arith/common/sim.py.
`timescale 1ns/1ps
module tb_stream #(
    parameter int IN_W    = 8,
    parameter int OUT_W   = 8,
    parameter int NVEC    = 16,
    parameter int LAT     = 1,       // expected latency, clock edges
    parameter int GAP_PCT = 0,       // percent of cycles on which a pending input is withheld
    parameter int SEED    = 1
) (
    output logic             clk,
    output logic             rst,
    output logic             in_valid,
    input  logic             in_ready,
    output logic [IN_W-1:0]  in_data,
    input  logic             out_valid,
    input  logic [OUT_W-1:0] out_data
);
    logic [IN_W-1:0]  vin  [0:NVEC-1];
    logic [OUT_W-1:0] vexp [0:NVEC-1];
    string fin, fexp;
    integer seed;
    integer sent, got, mism, lat_err, spurious, cyc, xcount;
    integer acc_cyc [0:NVEC-1];
    logic   running;

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        if (!$value$plusargs("vin=%s", fin) || !$value$plusargs("vexp=%s", fexp)) begin
            $display("ARITH_RESULT error=missing_plusargs");
            $finish;
        end
        $readmemh(fin, vin);
        $readmemh(fexp, vexp);
        seed = SEED;
        sent = 0; got = 0; mism = 0; lat_err = 0; spurious = 0; xcount = 0; cyc = 0;
        rst = 1'b1; in_valid = 1'b0; in_data = '0; running = 1'b0;
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        running <= 1'b1;
    end

    // Driver and checker share one clocked process: everything is sampled from the values before this edge.
    always @(posedge clk) begin
        if (running) begin
            cyc <= cyc + 1;
            // output side
            if (out_valid === 1'bx) xcount <= xcount + 1;
            if (out_valid === 1'b1) begin
                if (got >= sent) spurious <= spurious + 1;
                else begin
                    if (out_data !== vexp[got]) begin
                        mism <= mism + 1;
                        if (mism < 5) $display("MISMATCH idx=%0d in=%h got=%h exp=%h", got, vin[got], out_data, vexp[got]);
                    end
                    if ((cyc - acc_cyc[got]) != LAT) begin
                        lat_err <= lat_err + 1;
                        if (lat_err < 5) $display("LATENCY idx=%0d measured=%0d expected=%0d", got, cyc - acc_cyc[got], LAT);
                    end
                end
                got <= got + 1;
            end
            // input side: the beat accepted on this edge
            if (in_valid && in_ready) begin
                acc_cyc[sent] = cyc;
                sent <= sent + 1;
                in_valid <= 1'b0;
            end
            if ((!in_valid || in_ready) && (sent + ((in_valid && in_ready) ? 1 : 0)) < NVEC) begin
                if (($random(seed) & 32'h7fffffff) % 100 >= GAP_PCT) begin
                    in_valid <= 1'b1;
                    in_data  <= vin[sent + ((in_valid && in_ready) ? 1 : 0)];
                end else begin
                    in_valid <= 1'b0;
                end
            end
            if (got >= NVEC || cyc > (NVEC + 4) * (LAT + 8) * 4) begin
                $display("ARITH_RESULT checked=%0d mismatches=%0d lat_errors=%0d spurious=%0d x_valid=%0d sent=%0d done=%0d",
                         got, mism, lat_err, spurious, xcount, sent, (got >= NVEC) ? 1 : 0);
                $finish;
            end
        end
    end
endmodule
