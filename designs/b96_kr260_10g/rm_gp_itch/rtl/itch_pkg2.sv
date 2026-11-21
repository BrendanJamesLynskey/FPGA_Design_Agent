// itch_pkg2.sv: the layout of the ITCH path's two host vectors (brief 127): CFG2 (register domain -> core clock) and STAT2 (core clock -> register domain), as 32-bit word indices.
// designs/b96_kr260_10g/rm_gp_itch/regmap_itch.py holds the same list as data and tests/test_b127_regmap.py checks that the two agree; do not edit one without the other.
package itch_pkg2;
    localparam int NCW = 32;       // words of CFG2
    localparam int C_CTRL = 0, C_THR = 1, C_QTY = 2, C_MAXQTY = 3, C_MAXPOS = 4, C_BAND = 5, C_PXOFF = 6, C_MINQTY = 7, C_ORDF0 = 8, C_ORDF1 = 9, C_WATCH = 10,
                   C_FEEDIP = 18, C_FEEDPORT = 19, C_TCPSEQ = 20, C_TCPACK = 21, C_CMD = 22, C_RPW = 23, C_RPWLO = 24, C_RPWHI = 25, C_CAPADDR = 26, C_TCPFA = 27, C_TCPFD = 28, C_RPCFG = 29;
    // CTRL bits
    localparam int K_EN = 0, K_ARM = 1, K_KILL = 2, K_SPEC = 3, K_HALT = 4, K_STRICT = 5;
    // CMD bits (a command is executed once when CMD[23:16] changes)
    localparam int M_CLR_CNT = 0, M_CLR_FLAGS = 1, M_CLR_BOOK = 2, M_CLR_POS = 3, M_CLR_REF = 4, M_RP_START = 5, M_TCP_LOAD = 6, M_LAT_CLR = 7, M_CAP_CLR = 8, M_RP_STOP = 9;

    localparam int NSW = 96;       // words of STAT2
    localparam int S_ITCH = 0;     // 45 counters of brief 110, in the order of itch_pkg
    localparam int S_US = 45;      // 15 counters of udp_strip
    localparam int S_O_SENT = 60, S_O_PZ_ABORT = 61, S_O_PZ_BAD = 62, S_O_PZ_STRICT = 63, S_O_UNV = 64, S_O_DROP = 65, S_O_OFL = 66, S_O_UNRES = 67, S_O_LATE = 68;
    localparam int S_RP_FRAMES = 69, S_RP_STAT = 70;
    localparam int S_LAT_LAST = 71, S_LAT_MIN = 72, S_LAT_MAX = 73, S_LAT_CNT = 74, S_LAT_NEG = 75, S_HIST = 76;     // 76..83: 16 bins of 16 bits
    localparam int S_TS_EOF = 84, S_TS_GO = 85, S_TS_SOP = 86, S_TS_RXSOP = 87, S_FLAGS = 88, S_CAP_LO = 89, S_CAP_HI = 90, S_CAP_ECHO = 91, S_TCPF_RD = 92, S_TCPF_ECHO = 93, S_CMD_ECHO = 94, S_TCPFD_ECHO = 95;
endpackage
