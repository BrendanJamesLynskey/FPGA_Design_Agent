`timescale 1ns / 1ps
// rig_pkg.sv: variant codes and the placement of each copy (reports/11_cdc_soak_rig_design.md sections 1-3).
//
// Copy k of a variant gets a direction and a placement class, so every (direction, class) pair appears once in
// any 9 consecutive copies:  dir = k mod 3 (0 a->b, 1 b->a, 2 a->c);  cls = (k + k/3) mod 3 (0 far, 1 near,
// 2 boundary). M6b/M6c always run f->b (f = 250 MHz). Domains: 0 a (100 MHz oscillator), 1 b (STARTUPE2
// CFGMCLK), 2 c (MMCM output stepped by dynamic fine phase shift), 3 f (250 MHz MMCM output, source only).

package rig_pkg;
    localparam int NVAR = 28;
    // correct variants
    localparam int V_C1 = 0, V_C2 = 1, V_C3A = 2, V_C3B = 3, V_C4 = 4, V_C5 = 5, V_C6 = 6, V_C7 = 7, V_C8 = 8,
                   V_C9 = 9, V_C10 = 10, V_C11 = 11, V_C12 = 12, V_C13 = 13;
    // mutants
    localparam int V_M1 = 14, V_M1B = 15, V_M2 = 16, V_M3 = 17, V_M4 = 18, V_M5 = 19, V_M6A = 20, V_M6B = 21,
                   V_M6C = 22, V_M7 = 23, V_M8 = 24, V_M9 = 25, V_M10 = 26, V_M11 = 27;

    localparam int D_A = 0, D_B = 1, D_C = 2, D_F = 3;

    function automatic int dir_of(input int k);
        return k % 3;
    endfunction

    function automatic int cls_of(input int k);
        return (k + k / 3) % 3;
    endfunction

    function automatic int sdom(input int v, input int k);
        if (v == V_M6B || v == V_M6C) return D_F;
        case (dir_of(k))
            0:       return D_A;
            1:       return D_B;
            default: return D_A;
        endcase
    endfunction

    function automatic int ddom(input int v, input int k);
        if (v == V_M6B || v == V_M6C) return D_B;
        case (dir_of(k))
            0:       return D_B;
            1:       return D_A;
            default: return D_C;
        endcase
    endfunction

    // variant groups: 0 single-bit and pulse, 1 counters, 2 handshakes, 3 FIFOs, 4 reset release, 5 M8
    function automatic int grp_of(input int v);
        case (v)
            V_C1, V_C2, V_C3A, V_C3B, V_C4, V_C5, V_M1, V_M1B, V_M2, V_M4, V_M5, V_M7: return 0;
            V_C6, V_C7, V_M3, V_M6A, V_M6B, V_M6C:                                     return 1;
            V_C8, V_C9, V_M11:                                                         return 2;
            V_C10, V_C11, V_C13, V_M9:                                                 return 3;
            V_C12, V_M10:                                                              return 4;
            default:                                                                   return 5;
        endcase
    endfunction

    // variants that take part in the reset storms
    function automatic bit stormed(input int v);
        return v == V_C11 || v == V_C12 || v == V_C13 || v == V_M8 || v == V_M9 || v == V_M10 || v == V_M11;
    endfunction

    function automatic logic [15:0] prbs16_next(input logic [15:0] w);
        return {w[14:0], w[15] ^ w[13] ^ w[12] ^ w[10]};
    endfunction

    function automatic logic [11:0] bin2gray12(input logic [11:0] b);
        return b ^ (b >> 1);
    endfunction

    function automatic logic [11:0] gray2bin12(input logic [11:0] g);
        logic [11:0] b;
        b[11] = g[11];
        for (int i = 10; i >= 0; i--) b[i] = b[i+1] ^ g[i];
        return b;
    endfunction

    function automatic int popcount12(input logic [11:0] x);
        int n = 0;
        for (int i = 0; i < 12; i++) n += x[i];
        return n;
    endfunction
endpackage
