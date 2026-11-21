// ml_pkg.sv (brief 113): constants shared by the ML decision stage of build rm_gp_ml (ml_stage, trade64, rx_path, b96_core).
package ml_pkg;
    localparam int NMLW = 14;     // 32-bit status words of the stage (docs/ml_registers.md, MLV0..MLV13)
endpackage
