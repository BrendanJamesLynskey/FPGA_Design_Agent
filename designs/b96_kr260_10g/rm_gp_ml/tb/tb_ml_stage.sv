`timescale 1ns/1ps
// tb_ml_stage.sv (brief 113): ml_stage with gbt_comb on its own, driven by a stimulus file written by tests/test_b113_stage_rtl.py (the Python twin's events).
// Each line of the file: op a b c d e f g, in the clock it is read.   op 0: idle for `a` clocks.   op 1: observation (inst a, type b, side c, price d, size e, decision-wanted f).
// op 2: end of frame (good = a).   op 3: state reset pulse.   op 4: counter clear pulse.
// Prints, at an observation, "OBS <feat hex> <cls> <agree> <cls_ok>" (mid-clock, the values the decision would read) and at the end "MLV <i> <value>" for the 14 status words.
module tb_ml_stage;
    logic clk = 0, rst = 1, clr = 0, st_rst = 0, obs_v = 0, dec_v = 0, end_v = 0, end_good = 0, obs_side = 0;
    logic [15:0] ml_inst = 16'd3, obs_inst = 0;
    logic [7:0]  obs_type = 0;
    logic [31:0] obs_px = 0, obs_sz = 0;
    logic        en_veto = 1;
    logic        agree;
    logic [32 * ml_pkg::NMLW - 1:0] ml_vec;
    always #5 clk = ~clk;
    ml_stage u (.clk, .rst, .clr, .st_rst, .ml_inst, .en_veto, .obs_v, .obs_inst, .obs_type, .obs_side, .obs_px, .obs_sz, .dec_v, .end_v, .end_good, .agree, .ml_vec);
    integer fd, op, a, b, c, d, e, f, r;
    initial begin
        fd = $fopen("stim.txt", "r");
        if (fd == 0) begin $display("NO stim.txt"); $finish; end
        repeat (4) @(posedge clk);
        #1 rst = 0;
        repeat (6) @(posedge clk);
        while (!$feof(fd)) begin
            r = $fscanf(fd, "%d %d %d %d %d %d %d\n", op, a, b, c, d, e, f);
            if (r == 7) begin
                case (op)
                    0: repeat (a) @(posedge clk);
                    1: begin
                        #1 obs_v = 1; obs_inst = a; obs_type = b; obs_side = c; obs_px = d; obs_sz = e; dec_v = f;
                        #3 $display("OBS %h %0d %b %b", u.feat_r, u.cls, u.agree, u.cls_ok);
                        @(posedge clk); #1 obs_v = 0; dec_v = 0;
                    end
                    2: begin #1 end_v = 1; end_good = a; @(posedge clk); #1 end_v = 0; end_good = 0; end
                    3: begin #1 st_rst = 1; @(posedge clk); #1 st_rst = 0; end
                    4: begin #1 clr = 1; @(posedge clk); #1 clr = 0; end
                    default: ;
                endcase
            end
        end
        repeat (8) @(posedge clk);
        for (int i = 0; i < ml_pkg::NMLW; i++) $display("MLV %0d %0d", i, ml_vec[32 * i +: 32]);
        $finish;
    end
endmodule
