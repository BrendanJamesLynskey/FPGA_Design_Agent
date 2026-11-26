module pipe_reg_hc_w4_n1_m0_000 (
    s_axis_tdata,
    aresetn,
    aclk,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _22;
    wire [3:0] _17;
    wire [3:0] _24;
    wire [3:0] _25;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _30;
    wire [3:0] _33;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _37;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire vdd;
    wire _19;
    wire rst;
    wire _38;
    wire _12;
    reg g0_m_valid;
    wire _28;
    wire _29;
    assign _22 = g0_m_valid & m_axis_tready;
    assign _17 = 4'b0000;
    assign _24 = 4'b0001;
    assign _25 = f_out + _24;
    assign _1 = _25;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _17;
        else
            if (_22)
                f_out <= _1;
    end
    assign _30 = s_axis_tvalid & _29;
    assign _33 = f_in + _24;
    assign _3 = _33;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _17;
        else
            if (_30)
                f_in <= _3;
    end
    assign _37 = _29 ? s_axis_tdata : g0_m_data;
    assign _6 = _37;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign vdd = 1'b1;
    assign _19 = 1'b0;
    assign rst = ~ aresetn;
    assign _38 = _29 ? s_axis_tvalid : g0_m_valid;
    assign _12 = _38;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _19;
        else
            g0_m_valid <= _12;
    end
    assign _28 = ~ g0_m_valid;
    assign _29 = m_axis_tready | _28;
    assign s_axis_tready = _29;
    assign m_axis_tvalid = g0_m_valid;
    assign m_axis_tdata = g0_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n3_m0_000 (
    s_axis_tdata,
    aresetn,
    aclk,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _26;
    wire [3:0] _21;
    wire [3:0] _28;
    wire [3:0] _29;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _34;
    wire [3:0] _37;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _41;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire [3:0] _45;
    wire [3:0] _7;
    reg [3:0] g1_m_data;
    wire [3:0] _49;
    wire [3:0] _8;
    reg [3:0] g2_m_data;
    wire _23;
    wire vdd;
    wire rst;
    wire _53;
    wire _14;
    reg g0_m_valid;
    wire _57;
    wire _15;
    reg g1_m_valid;
    wire _58;
    wire _16;
    reg g2_m_valid;
    wire _32;
    wire _33;
    assign _26 = g2_m_valid & m_axis_tready;
    assign _21 = 4'b0000;
    assign _28 = 4'b0001;
    assign _29 = f_out + _28;
    assign _1 = _29;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _21;
        else
            if (_26)
                f_out <= _1;
    end
    assign _34 = s_axis_tvalid & _33;
    assign _37 = f_in + _28;
    assign _3 = _37;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _21;
        else
            if (_34)
                f_in <= _3;
    end
    assign _41 = _33 ? s_axis_tdata : g0_m_data;
    assign _6 = _41;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign _45 = _33 ? g0_m_data : g1_m_data;
    assign _7 = _45;
    always @(posedge aclk) begin
        g1_m_data <= _7;
    end
    assign _49 = _33 ? g1_m_data : g2_m_data;
    assign _8 = _49;
    always @(posedge aclk) begin
        g2_m_data <= _8;
    end
    assign _23 = 1'b0;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _53 = _33 ? s_axis_tvalid : g0_m_valid;
    assign _14 = _53;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _23;
        else
            g0_m_valid <= _14;
    end
    assign _57 = _33 ? g0_m_valid : g1_m_valid;
    assign _15 = _57;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _23;
        else
            g1_m_valid <= _15;
    end
    assign _58 = _33 ? g1_m_valid : g2_m_valid;
    assign _16 = _58;
    always @(posedge aclk) begin
        if (rst)
            g2_m_valid <= _23;
        else
            g2_m_valid <= _16;
    end
    assign _32 = ~ g2_m_valid;
    assign _33 = m_axis_tready | _32;
    assign s_axis_tready = _33;
    assign m_axis_tvalid = g2_m_valid;
    assign m_axis_tdata = g2_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n1_m1_000 (
    s_axis_tdata,
    aresetn,
    aclk,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _26;
    wire [3:0] _21;
    wire [3:0] _28;
    wire [3:0] _29;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _32;
    wire [3:0] _35;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _50;
    wire [3:0] _44;
    wire [3:0] _45;
    wire [3:0] _6;
    reg [3:0] g0_t_data;
    wire [3:0] _49;
    wire [3:0] _51;
    wire [3:0] _7;
    reg [3:0] g0_m_data;
    wire _37;
    wire _64;
    wire _63;
    wire _65;
    wire vdd;
    wire rst;
    wire _56;
    wire _55;
    wire _57;
    wire _13;
    reg g0_m_valid;
    wire _42;
    wire _43;
    wire _60;
    wire _59;
    wire _61;
    wire _14;
    reg g0_t_valid;
    wire _62;
    wire _66;
    wire _67;
    wire _16;
    reg g0_s_ready;
    wire _17;
    assign _26 = g0_m_valid & m_axis_tready;
    assign _21 = 4'b0000;
    assign _28 = 4'b0001;
    assign _29 = f_out + _28;
    assign _1 = _29;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _21;
        else
            if (_26)
                f_out <= _1;
    end
    assign _32 = s_axis_tvalid & _17;
    assign _35 = f_in + _28;
    assign _3 = _35;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _21;
        else
            if (_32)
                f_in <= _3;
    end
    assign _50 = _43 ? s_axis_tdata : g0_m_data;
    assign _44 = _43 ? g0_t_data : s_axis_tdata;
    assign _45 = g0_s_ready ? _44 : g0_t_data;
    assign _6 = _45;
    always @(posedge aclk) begin
        g0_t_data <= _6;
    end
    assign _49 = m_axis_tready ? g0_t_data : g0_m_data;
    assign _51 = g0_s_ready ? _50 : _49;
    assign _7 = _51;
    always @(posedge aclk) begin
        g0_m_data <= _7;
    end
    assign _37 = 1'b0;
    assign _64 = ~ s_axis_tvalid;
    assign _63 = ~ g0_m_valid;
    assign _65 = _63 | _64;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _56 = _43 ? s_axis_tvalid : g0_m_valid;
    assign _55 = m_axis_tready ? g0_t_valid : g0_m_valid;
    assign _57 = g0_s_ready ? _56 : _55;
    assign _13 = _57;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _37;
        else
            g0_m_valid <= _13;
    end
    assign _42 = ~ g0_m_valid;
    assign _43 = m_axis_tready | _42;
    assign _60 = _43 ? g0_t_valid : s_axis_tvalid;
    assign _59 = m_axis_tready ? _37 : g0_t_valid;
    assign _61 = g0_s_ready ? _60 : _59;
    assign _14 = _61;
    always @(posedge aclk) begin
        if (rst)
            g0_t_valid <= _37;
        else
            g0_t_valid <= _14;
    end
    assign _62 = ~ g0_t_valid;
    assign _66 = _62 & _65;
    assign _67 = m_axis_tready | _66;
    assign _16 = _67;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _37;
        else
            g0_s_ready <= _16;
    end
    assign _17 = g0_s_ready;
    assign s_axis_tready = _17;
    assign m_axis_tvalid = g0_m_valid;
    assign m_axis_tdata = g0_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n2_m1_000 (
    s_axis_tdata,
    aresetn,
    aclk,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _32;
    wire [3:0] _27;
    wire [3:0] _34;
    wire [3:0] _35;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _38;
    wire [3:0] _41;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _75;
    wire [3:0] _59;
    wire [3:0] _53;
    wire [3:0] _54;
    wire [3:0] _6;
    reg [3:0] g0_t_data;
    wire [3:0] _58;
    wire [3:0] _60;
    wire [3:0] _7;
    reg [3:0] g0_m_data;
    wire [3:0] _69;
    wire [3:0] _70;
    wire [3:0] _8;
    reg [3:0] g1_t_data;
    wire [3:0] _74;
    wire [3:0] _76;
    wire [3:0] _9;
    reg [3:0] g1_m_data;
    wire _43;
    wire _105;
    wire _104;
    wire _106;
    wire _103;
    wire _107;
    wire _99;
    wire _98;
    wire _100;
    wire _85;
    wire vdd;
    wire rst;
    wire _51;
    wire _52;
    wire _82;
    wire _81;
    wire _83;
    wire _15;
    reg g0_t_valid;
    wire _84;
    wire _86;
    wire _16;
    reg g0_m_valid;
    wire _91;
    wire _90;
    wire _92;
    wire _17;
    reg g1_m_valid;
    wire _67;
    wire _68;
    wire _95;
    wire _94;
    wire _96;
    wire _18;
    reg g1_t_valid;
    wire _97;
    wire _101;
    wire _102;
    wire _20;
    reg g1_s_ready;
    wire _21;
    wire _108;
    wire _22;
    reg g0_s_ready;
    wire _23;
    assign _32 = g1_m_valid & m_axis_tready;
    assign _27 = 4'b0000;
    assign _34 = 4'b0001;
    assign _35 = f_out + _34;
    assign _1 = _35;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _27;
        else
            if (_32)
                f_out <= _1;
    end
    assign _38 = s_axis_tvalid & _23;
    assign _41 = f_in + _34;
    assign _3 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _27;
        else
            if (_38)
                f_in <= _3;
    end
    assign _75 = _68 ? g0_m_data : g1_m_data;
    assign _59 = _52 ? s_axis_tdata : g0_m_data;
    assign _53 = _52 ? g0_t_data : s_axis_tdata;
    assign _54 = g0_s_ready ? _53 : g0_t_data;
    assign _6 = _54;
    always @(posedge aclk) begin
        g0_t_data <= _6;
    end
    assign _58 = _21 ? g0_t_data : g0_m_data;
    assign _60 = g0_s_ready ? _59 : _58;
    assign _7 = _60;
    always @(posedge aclk) begin
        g0_m_data <= _7;
    end
    assign _69 = _68 ? g1_t_data : g0_m_data;
    assign _70 = g1_s_ready ? _69 : g1_t_data;
    assign _8 = _70;
    always @(posedge aclk) begin
        g1_t_data <= _8;
    end
    assign _74 = m_axis_tready ? g1_t_data : g1_m_data;
    assign _76 = g1_s_ready ? _75 : _74;
    assign _9 = _76;
    always @(posedge aclk) begin
        g1_m_data <= _9;
    end
    assign _43 = 1'b0;
    assign _105 = ~ s_axis_tvalid;
    assign _104 = ~ g0_m_valid;
    assign _106 = _104 | _105;
    assign _103 = ~ g0_t_valid;
    assign _107 = _103 & _106;
    assign _99 = ~ g0_m_valid;
    assign _98 = ~ g1_m_valid;
    assign _100 = _98 | _99;
    assign _85 = _52 ? s_axis_tvalid : g0_m_valid;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _51 = ~ g0_m_valid;
    assign _52 = _21 | _51;
    assign _82 = _52 ? g0_t_valid : s_axis_tvalid;
    assign _81 = _21 ? _43 : g0_t_valid;
    assign _83 = g0_s_ready ? _82 : _81;
    assign _15 = _83;
    always @(posedge aclk) begin
        if (rst)
            g0_t_valid <= _43;
        else
            g0_t_valid <= _15;
    end
    assign _84 = _21 ? g0_t_valid : g0_m_valid;
    assign _86 = g0_s_ready ? _85 : _84;
    assign _16 = _86;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _43;
        else
            g0_m_valid <= _16;
    end
    assign _91 = _68 ? g0_m_valid : g1_m_valid;
    assign _90 = m_axis_tready ? g1_t_valid : g1_m_valid;
    assign _92 = g1_s_ready ? _91 : _90;
    assign _17 = _92;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _43;
        else
            g1_m_valid <= _17;
    end
    assign _67 = ~ g1_m_valid;
    assign _68 = m_axis_tready | _67;
    assign _95 = _68 ? g1_t_valid : g0_m_valid;
    assign _94 = m_axis_tready ? _43 : g1_t_valid;
    assign _96 = g1_s_ready ? _95 : _94;
    assign _18 = _96;
    always @(posedge aclk) begin
        if (rst)
            g1_t_valid <= _43;
        else
            g1_t_valid <= _18;
    end
    assign _97 = ~ g1_t_valid;
    assign _101 = _97 & _100;
    assign _102 = m_axis_tready | _101;
    assign _20 = _102;
    always @(posedge aclk) begin
        if (rst)
            g1_s_ready <= _43;
        else
            g1_s_ready <= _20;
    end
    assign _21 = g1_s_ready;
    assign _108 = _21 | _107;
    assign _22 = _108;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _43;
        else
            g0_s_ready <= _22;
    end
    assign _23 = g0_s_ready;
    assign s_axis_tready = _23;
    assign m_axis_tvalid = g1_m_valid;
    assign m_axis_tdata = g1_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n3_m1_000 (
    s_axis_tdata,
    aresetn,
    aclk,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _38;
    wire [3:0] _33;
    wire [3:0] _40;
    wire [3:0] _41;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _44;
    wire [3:0] _47;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _100;
    wire [3:0] _84;
    wire [3:0] _65;
    wire [3:0] _59;
    wire [3:0] _60;
    wire [3:0] _6;
    reg [3:0] g0_t_data;
    wire [3:0] _64;
    wire [3:0] _66;
    wire [3:0] _7;
    reg [3:0] g0_m_data;
    wire [3:0] _78;
    wire [3:0] _79;
    wire [3:0] _8;
    reg [3:0] g1_t_data;
    wire [3:0] _83;
    wire [3:0] _85;
    wire [3:0] _9;
    reg [3:0] g1_m_data;
    wire [3:0] _94;
    wire [3:0] _95;
    wire [3:0] _10;
    reg [3:0] g2_t_data;
    wire [3:0] _99;
    wire [3:0] _101;
    wire [3:0] _11;
    reg [3:0] g2_m_data;
    wire _49;
    wire _146;
    wire _145;
    wire _147;
    wire _144;
    wire _148;
    wire _140;
    wire _139;
    wire _141;
    wire _138;
    wire _142;
    wire _134;
    wire _133;
    wire _135;
    wire _120;
    wire _110;
    wire vdd;
    wire rst;
    wire _57;
    wire _58;
    wire _107;
    wire _106;
    wire _108;
    wire _17;
    reg g0_t_valid;
    wire _109;
    wire _111;
    wire _18;
    reg g0_m_valid;
    wire _76;
    wire _77;
    wire _117;
    wire _116;
    wire _118;
    wire _19;
    reg g1_t_valid;
    wire _119;
    wire _121;
    wire _20;
    reg g1_m_valid;
    wire _126;
    wire _125;
    wire _127;
    wire _21;
    reg g2_m_valid;
    wire _92;
    wire _93;
    wire _130;
    wire _129;
    wire _131;
    wire _22;
    reg g2_t_valid;
    wire _132;
    wire _136;
    wire _137;
    wire _24;
    reg g2_s_ready;
    wire _25;
    wire _143;
    wire _26;
    reg g1_s_ready;
    wire _27;
    wire _149;
    wire _28;
    reg g0_s_ready;
    wire _29;
    assign _38 = g2_m_valid & m_axis_tready;
    assign _33 = 4'b0000;
    assign _40 = 4'b0001;
    assign _41 = f_out + _40;
    assign _1 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _33;
        else
            if (_38)
                f_out <= _1;
    end
    assign _44 = s_axis_tvalid & _29;
    assign _47 = f_in + _40;
    assign _3 = _47;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _33;
        else
            if (_44)
                f_in <= _3;
    end
    assign _100 = _93 ? g1_m_data : g2_m_data;
    assign _84 = _77 ? g0_m_data : g1_m_data;
    assign _65 = _58 ? s_axis_tdata : g0_m_data;
    assign _59 = _58 ? g0_t_data : s_axis_tdata;
    assign _60 = g0_s_ready ? _59 : g0_t_data;
    assign _6 = _60;
    always @(posedge aclk) begin
        g0_t_data <= _6;
    end
    assign _64 = _27 ? g0_t_data : g0_m_data;
    assign _66 = g0_s_ready ? _65 : _64;
    assign _7 = _66;
    always @(posedge aclk) begin
        g0_m_data <= _7;
    end
    assign _78 = _77 ? g1_t_data : g0_m_data;
    assign _79 = g1_s_ready ? _78 : g1_t_data;
    assign _8 = _79;
    always @(posedge aclk) begin
        g1_t_data <= _8;
    end
    assign _83 = _25 ? g1_t_data : g1_m_data;
    assign _85 = g1_s_ready ? _84 : _83;
    assign _9 = _85;
    always @(posedge aclk) begin
        g1_m_data <= _9;
    end
    assign _94 = _93 ? g2_t_data : g1_m_data;
    assign _95 = g2_s_ready ? _94 : g2_t_data;
    assign _10 = _95;
    always @(posedge aclk) begin
        g2_t_data <= _10;
    end
    assign _99 = m_axis_tready ? g2_t_data : g2_m_data;
    assign _101 = g2_s_ready ? _100 : _99;
    assign _11 = _101;
    always @(posedge aclk) begin
        g2_m_data <= _11;
    end
    assign _49 = 1'b0;
    assign _146 = ~ s_axis_tvalid;
    assign _145 = ~ g0_m_valid;
    assign _147 = _145 | _146;
    assign _144 = ~ g0_t_valid;
    assign _148 = _144 & _147;
    assign _140 = ~ g0_m_valid;
    assign _139 = ~ g1_m_valid;
    assign _141 = _139 | _140;
    assign _138 = ~ g1_t_valid;
    assign _142 = _138 & _141;
    assign _134 = ~ g1_m_valid;
    assign _133 = ~ g2_m_valid;
    assign _135 = _133 | _134;
    assign _120 = _77 ? g0_m_valid : g1_m_valid;
    assign _110 = _58 ? s_axis_tvalid : g0_m_valid;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _57 = ~ g0_m_valid;
    assign _58 = _27 | _57;
    assign _107 = _58 ? g0_t_valid : s_axis_tvalid;
    assign _106 = _27 ? _49 : g0_t_valid;
    assign _108 = g0_s_ready ? _107 : _106;
    assign _17 = _108;
    always @(posedge aclk) begin
        if (rst)
            g0_t_valid <= _49;
        else
            g0_t_valid <= _17;
    end
    assign _109 = _27 ? g0_t_valid : g0_m_valid;
    assign _111 = g0_s_ready ? _110 : _109;
    assign _18 = _111;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _49;
        else
            g0_m_valid <= _18;
    end
    assign _76 = ~ g1_m_valid;
    assign _77 = _25 | _76;
    assign _117 = _77 ? g1_t_valid : g0_m_valid;
    assign _116 = _25 ? _49 : g1_t_valid;
    assign _118 = g1_s_ready ? _117 : _116;
    assign _19 = _118;
    always @(posedge aclk) begin
        if (rst)
            g1_t_valid <= _49;
        else
            g1_t_valid <= _19;
    end
    assign _119 = _25 ? g1_t_valid : g1_m_valid;
    assign _121 = g1_s_ready ? _120 : _119;
    assign _20 = _121;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _49;
        else
            g1_m_valid <= _20;
    end
    assign _126 = _93 ? g1_m_valid : g2_m_valid;
    assign _125 = m_axis_tready ? g2_t_valid : g2_m_valid;
    assign _127 = g2_s_ready ? _126 : _125;
    assign _21 = _127;
    always @(posedge aclk) begin
        if (rst)
            g2_m_valid <= _49;
        else
            g2_m_valid <= _21;
    end
    assign _92 = ~ g2_m_valid;
    assign _93 = m_axis_tready | _92;
    assign _130 = _93 ? g2_t_valid : g1_m_valid;
    assign _129 = m_axis_tready ? _49 : g2_t_valid;
    assign _131 = g2_s_ready ? _130 : _129;
    assign _22 = _131;
    always @(posedge aclk) begin
        if (rst)
            g2_t_valid <= _49;
        else
            g2_t_valid <= _22;
    end
    assign _132 = ~ g2_t_valid;
    assign _136 = _132 & _135;
    assign _137 = m_axis_tready | _136;
    assign _24 = _137;
    always @(posedge aclk) begin
        if (rst)
            g2_s_ready <= _49;
        else
            g2_s_ready <= _24;
    end
    assign _25 = g2_s_ready;
    assign _143 = _25 | _142;
    assign _26 = _143;
    always @(posedge aclk) begin
        if (rst)
            g1_s_ready <= _49;
        else
            g1_s_ready <= _26;
    end
    assign _27 = g1_s_ready;
    assign _149 = _27 | _148;
    assign _28 = _149;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _49;
        else
            g0_s_ready <= _28;
    end
    assign _29 = g0_s_ready;
    assign s_axis_tready = _29;
    assign m_axis_tvalid = g2_m_valid;
    assign m_axis_tdata = g2_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n1_m2_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _28;
    wire [3:0] _23;
    wire [3:0] _30;
    wire [3:0] _31;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _34;
    wire [3:0] _37;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _48;
    wire [3:0] _49;
    wire [3:0] _5;
    reg [3:0] g0_e1;
    wire _46;
    wire _50;
    wire _51;
    wire _7;
    reg g0_wp;
    wire [3:0] _55;
    wire [3:0] _56;
    wire [3:0] _8;
    reg [3:0] g0_e0;
    wire _61;
    wire _62;
    wire _9;
    reg g0_rp;
    wire [3:0] _63;
    wire [1:0] _80;
    wire [1:0] _74;
    wire [1:0] _75;
    wire [1:0] _72;
    wire [1:0] _69;
    wire [1:0] _12;
    reg [1:0] g0_cnt;
    wire _66;
    wire _67;
    wire [1:0] _73;
    wire vdd;
    wire rst;
    wire _78;
    wire _79;
    wire _16;
    reg g0_m_valid;
    wire _57;
    wire _64;
    wire _41;
    wire _65;
    wire [1:0] _76;
    wire _81;
    wire _82;
    wire _18;
    reg g0_s_ready;
    wire _19;
    assign _28 = g0_m_valid & m_axis_tready;
    assign _23 = 4'b0000;
    assign _30 = 4'b0001;
    assign _31 = f_out + _30;
    assign _1 = _31;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _23;
        else
            if (_28)
                f_out <= _1;
    end
    assign _34 = s_axis_tvalid & _19;
    assign _37 = f_in + _30;
    assign _3 = _37;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _23;
        else
            if (_34)
                f_in <= _3;
    end
    assign _48 = g0_wp ? s_axis_tdata : g0_e1;
    assign _49 = _41 ? _48 : g0_e1;
    assign _5 = _49;
    always @(posedge aclk) begin
        g0_e1 <= _5;
    end
    assign _46 = 1'b0;
    assign _50 = ~ g0_wp;
    assign _51 = _41 ? _50 : g0_wp;
    assign _7 = _51;
    always @(posedge aclk) begin
        if (rst)
            g0_wp <= _46;
        else
            g0_wp <= _7;
    end
    assign _55 = g0_wp ? g0_e0 : s_axis_tdata;
    assign _56 = _41 ? _55 : g0_e0;
    assign _8 = _56;
    always @(posedge aclk) begin
        g0_e0 <= _8;
    end
    assign _61 = ~ g0_rp;
    assign _62 = _57 ? _61 : g0_rp;
    assign _9 = _62;
    always @(posedge aclk) begin
        if (rst)
            g0_rp <= _46;
        else
            g0_rp <= _9;
    end
    assign _63 = g0_rp ? g0_e1 : g0_e0;
    assign _80 = 2'b10;
    assign _74 = 2'b01;
    assign _75 = g0_cnt + _74;
    assign _72 = g0_cnt - _74;
    assign _69 = 2'b00;
    assign _12 = _76;
    always @(posedge aclk) begin
        if (rst)
            g0_cnt <= _69;
        else
            g0_cnt <= _12;
    end
    assign _66 = ~ _41;
    assign _67 = _66 & _57;
    assign _73 = _67 ? _72 : g0_cnt;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _78 = _76 == _69;
    assign _79 = ~ _78;
    assign _16 = _79;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _46;
        else
            g0_m_valid <= _16;
    end
    assign _57 = g0_m_valid & m_axis_tready;
    assign _64 = ~ _57;
    assign _41 = s_axis_tvalid & g0_s_ready;
    assign _65 = _41 & _64;
    assign _76 = _65 ? _75 : _73;
    assign _81 = _76 == _80;
    assign _82 = ~ _81;
    assign _18 = _82;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _46;
        else
            g0_s_ready <= _18;
    end
    assign _19 = g0_s_ready;
    assign s_axis_tready = _19;
    assign m_axis_tvalid = g0_m_valid;
    assign m_axis_tdata = _63;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n2_m2_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _36;
    wire [3:0] _31;
    wire [3:0] _38;
    wire [3:0] _39;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _42;
    wire [3:0] _45;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _69;
    wire [3:0] _70;
    wire [3:0] _5;
    reg [3:0] g1_e1;
    wire [3:0] _78;
    wire [3:0] _79;
    wire [3:0] _6;
    reg [3:0] g0_e1;
    wire _76;
    wire _80;
    wire _81;
    wire _8;
    reg g0_wp;
    wire [3:0] _82;
    wire [3:0] _83;
    wire [3:0] _9;
    reg [3:0] g0_e0;
    wire _85;
    wire _86;
    wire _10;
    reg g0_rp;
    wire [3:0] _68;
    wire _87;
    wire _88;
    wire _11;
    reg g1_wp;
    wire [3:0] _92;
    wire [3:0] _93;
    wire [3:0] _12;
    reg [3:0] g1_e0;
    wire _98;
    wire _99;
    wire _13;
    reg g1_rp;
    wire [3:0] _100;
    wire [1:0] _136;
    wire [1:0] _111;
    wire [1:0] _112;
    wire [1:0] _109;
    wire [1:0] _106;
    wire [1:0] _16;
    reg [1:0] g0_cnt;
    wire _103;
    wire _104;
    wire [1:0] _110;
    wire [1:0] _125;
    wire [1:0] _122;
    wire [1:0] _17;
    reg [1:0] g1_cnt;
    wire _116;
    wire _117;
    wire [1:0] _123;
    wire _128;
    wire _129;
    wire _19;
    reg g1_m_valid;
    wire _94;
    wire _114;
    wire _52;
    wire _115;
    wire [1:0] _126;
    wire _131;
    wire _132;
    wire _20;
    reg g1_s_ready;
    wire _21;
    wire vdd;
    wire rst;
    wire _134;
    wire _135;
    wire _24;
    reg g0_m_valid;
    wire _84;
    wire _101;
    wire _74;
    wire _102;
    wire [1:0] _113;
    wire _137;
    wire _138;
    wire _26;
    reg g0_s_ready;
    wire _27;
    assign _36 = g1_m_valid & m_axis_tready;
    assign _31 = 4'b0000;
    assign _38 = 4'b0001;
    assign _39 = f_out + _38;
    assign _1 = _39;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _31;
        else
            if (_36)
                f_out <= _1;
    end
    assign _42 = s_axis_tvalid & _27;
    assign _45 = f_in + _38;
    assign _3 = _45;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _31;
        else
            if (_42)
                f_in <= _3;
    end
    assign _69 = g1_wp ? _68 : g1_e1;
    assign _70 = _52 ? _69 : g1_e1;
    assign _5 = _70;
    always @(posedge aclk) begin
        g1_e1 <= _5;
    end
    assign _78 = g0_wp ? s_axis_tdata : g0_e1;
    assign _79 = _74 ? _78 : g0_e1;
    assign _6 = _79;
    always @(posedge aclk) begin
        g0_e1 <= _6;
    end
    assign _76 = 1'b0;
    assign _80 = ~ g0_wp;
    assign _81 = _74 ? _80 : g0_wp;
    assign _8 = _81;
    always @(posedge aclk) begin
        if (rst)
            g0_wp <= _76;
        else
            g0_wp <= _8;
    end
    assign _82 = g0_wp ? g0_e0 : s_axis_tdata;
    assign _83 = _74 ? _82 : g0_e0;
    assign _9 = _83;
    always @(posedge aclk) begin
        g0_e0 <= _9;
    end
    assign _85 = ~ g0_rp;
    assign _86 = _84 ? _85 : g0_rp;
    assign _10 = _86;
    always @(posedge aclk) begin
        if (rst)
            g0_rp <= _76;
        else
            g0_rp <= _10;
    end
    assign _68 = g0_rp ? g0_e1 : g0_e0;
    assign _87 = ~ g1_wp;
    assign _88 = _52 ? _87 : g1_wp;
    assign _11 = _88;
    always @(posedge aclk) begin
        if (rst)
            g1_wp <= _76;
        else
            g1_wp <= _11;
    end
    assign _92 = g1_wp ? g1_e0 : _68;
    assign _93 = _52 ? _92 : g1_e0;
    assign _12 = _93;
    always @(posedge aclk) begin
        g1_e0 <= _12;
    end
    assign _98 = ~ g1_rp;
    assign _99 = _94 ? _98 : g1_rp;
    assign _13 = _99;
    always @(posedge aclk) begin
        if (rst)
            g1_rp <= _76;
        else
            g1_rp <= _13;
    end
    assign _100 = g1_rp ? g1_e1 : g1_e0;
    assign _136 = 2'b10;
    assign _111 = 2'b01;
    assign _112 = g0_cnt + _111;
    assign _109 = g0_cnt - _111;
    assign _106 = 2'b00;
    assign _16 = _113;
    always @(posedge aclk) begin
        if (rst)
            g0_cnt <= _106;
        else
            g0_cnt <= _16;
    end
    assign _103 = ~ _74;
    assign _104 = _103 & _84;
    assign _110 = _104 ? _109 : g0_cnt;
    assign _125 = g1_cnt + _111;
    assign _122 = g1_cnt - _111;
    assign _17 = _126;
    always @(posedge aclk) begin
        if (rst)
            g1_cnt <= _106;
        else
            g1_cnt <= _17;
    end
    assign _116 = ~ _52;
    assign _117 = _116 & _94;
    assign _123 = _117 ? _122 : g1_cnt;
    assign _128 = _126 == _106;
    assign _129 = ~ _128;
    assign _19 = _129;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _76;
        else
            g1_m_valid <= _19;
    end
    assign _94 = g1_m_valid & m_axis_tready;
    assign _114 = ~ _94;
    assign _52 = g0_m_valid & g1_s_ready;
    assign _115 = _52 & _114;
    assign _126 = _115 ? _125 : _123;
    assign _131 = _126 == _136;
    assign _132 = ~ _131;
    assign _20 = _132;
    always @(posedge aclk) begin
        if (rst)
            g1_s_ready <= _76;
        else
            g1_s_ready <= _20;
    end
    assign _21 = g1_s_ready;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _134 = _113 == _106;
    assign _135 = ~ _134;
    assign _24 = _135;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _76;
        else
            g0_m_valid <= _24;
    end
    assign _84 = g0_m_valid & _21;
    assign _101 = ~ _84;
    assign _74 = s_axis_tvalid & g0_s_ready;
    assign _102 = _74 & _101;
    assign _113 = _102 ? _112 : _110;
    assign _137 = _113 == _136;
    assign _138 = ~ _137;
    assign _26 = _138;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _76;
        else
            g0_s_ready <= _26;
    end
    assign _27 = g0_s_ready;
    assign s_axis_tready = _27;
    assign m_axis_tvalid = g1_m_valid;
    assign m_axis_tdata = _100;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n3_m2_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _44;
    wire [3:0] _39;
    wire [3:0] _46;
    wire [3:0] _47;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _50;
    wire [3:0] _53;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _77;
    wire [3:0] _78;
    wire [3:0] _5;
    reg [3:0] g2_e1;
    wire [3:0] _99;
    wire [3:0] _100;
    wire [3:0] _6;
    reg [3:0] g1_e1;
    wire [3:0] _108;
    wire [3:0] _109;
    wire [3:0] _7;
    reg [3:0] g0_e1;
    wire _106;
    wire _110;
    wire _111;
    wire _9;
    reg g0_wp;
    wire [3:0] _112;
    wire [3:0] _113;
    wire [3:0] _10;
    reg [3:0] g0_e0;
    wire _115;
    wire _116;
    wire _11;
    reg g0_rp;
    wire [3:0] _98;
    wire _117;
    wire _118;
    wire _12;
    reg g1_wp;
    wire [3:0] _119;
    wire [3:0] _120;
    wire [3:0] _13;
    reg [3:0] g1_e0;
    wire _122;
    wire _123;
    wire _14;
    reg g1_rp;
    wire [3:0] _76;
    wire _124;
    wire _125;
    wire _15;
    reg g2_wp;
    wire [3:0] _129;
    wire [3:0] _130;
    wire [3:0] _16;
    reg [3:0] g2_e0;
    wire _135;
    wire _136;
    wire _17;
    reg g2_rp;
    wire [3:0] _137;
    wire [1:0] _192;
    wire [1:0] _148;
    wire [1:0] _149;
    wire [1:0] _146;
    wire [1:0] _143;
    wire [1:0] _20;
    reg [1:0] g0_cnt;
    wire _140;
    wire _141;
    wire [1:0] _147;
    wire [1:0] _162;
    wire [1:0] _159;
    wire [1:0] _21;
    reg [1:0] g1_cnt;
    wire _153;
    wire _154;
    wire [1:0] _160;
    wire [1:0] _175;
    wire [1:0] _172;
    wire [1:0] _22;
    reg [1:0] g2_cnt;
    wire _166;
    wire _167;
    wire [1:0] _173;
    wire _178;
    wire _179;
    wire _24;
    reg g2_m_valid;
    wire _131;
    wire _164;
    wire _60;
    wire _165;
    wire [1:0] _176;
    wire _181;
    wire _182;
    wire _25;
    reg g2_s_ready;
    wire _26;
    wire _184;
    wire _185;
    wire _27;
    reg g1_m_valid;
    wire _121;
    wire _151;
    wire _85;
    wire _152;
    wire [1:0] _163;
    wire _187;
    wire _188;
    wire _28;
    reg g1_s_ready;
    wire _29;
    wire vdd;
    wire rst;
    wire _190;
    wire _191;
    wire _32;
    reg g0_m_valid;
    wire _114;
    wire _138;
    wire _104;
    wire _139;
    wire [1:0] _150;
    wire _193;
    wire _194;
    wire _34;
    reg g0_s_ready;
    wire _35;
    assign _44 = g2_m_valid & m_axis_tready;
    assign _39 = 4'b0000;
    assign _46 = 4'b0001;
    assign _47 = f_out + _46;
    assign _1 = _47;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _39;
        else
            if (_44)
                f_out <= _1;
    end
    assign _50 = s_axis_tvalid & _35;
    assign _53 = f_in + _46;
    assign _3 = _53;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _39;
        else
            if (_50)
                f_in <= _3;
    end
    assign _77 = g2_wp ? _76 : g2_e1;
    assign _78 = _60 ? _77 : g2_e1;
    assign _5 = _78;
    always @(posedge aclk) begin
        g2_e1 <= _5;
    end
    assign _99 = g1_wp ? _98 : g1_e1;
    assign _100 = _85 ? _99 : g1_e1;
    assign _6 = _100;
    always @(posedge aclk) begin
        g1_e1 <= _6;
    end
    assign _108 = g0_wp ? s_axis_tdata : g0_e1;
    assign _109 = _104 ? _108 : g0_e1;
    assign _7 = _109;
    always @(posedge aclk) begin
        g0_e1 <= _7;
    end
    assign _106 = 1'b0;
    assign _110 = ~ g0_wp;
    assign _111 = _104 ? _110 : g0_wp;
    assign _9 = _111;
    always @(posedge aclk) begin
        if (rst)
            g0_wp <= _106;
        else
            g0_wp <= _9;
    end
    assign _112 = g0_wp ? g0_e0 : s_axis_tdata;
    assign _113 = _104 ? _112 : g0_e0;
    assign _10 = _113;
    always @(posedge aclk) begin
        g0_e0 <= _10;
    end
    assign _115 = ~ g0_rp;
    assign _116 = _114 ? _115 : g0_rp;
    assign _11 = _116;
    always @(posedge aclk) begin
        if (rst)
            g0_rp <= _106;
        else
            g0_rp <= _11;
    end
    assign _98 = g0_rp ? g0_e1 : g0_e0;
    assign _117 = ~ g1_wp;
    assign _118 = _85 ? _117 : g1_wp;
    assign _12 = _118;
    always @(posedge aclk) begin
        if (rst)
            g1_wp <= _106;
        else
            g1_wp <= _12;
    end
    assign _119 = g1_wp ? g1_e0 : _98;
    assign _120 = _85 ? _119 : g1_e0;
    assign _13 = _120;
    always @(posedge aclk) begin
        g1_e0 <= _13;
    end
    assign _122 = ~ g1_rp;
    assign _123 = _121 ? _122 : g1_rp;
    assign _14 = _123;
    always @(posedge aclk) begin
        if (rst)
            g1_rp <= _106;
        else
            g1_rp <= _14;
    end
    assign _76 = g1_rp ? g1_e1 : g1_e0;
    assign _124 = ~ g2_wp;
    assign _125 = _60 ? _124 : g2_wp;
    assign _15 = _125;
    always @(posedge aclk) begin
        if (rst)
            g2_wp <= _106;
        else
            g2_wp <= _15;
    end
    assign _129 = g2_wp ? g2_e0 : _76;
    assign _130 = _60 ? _129 : g2_e0;
    assign _16 = _130;
    always @(posedge aclk) begin
        g2_e0 <= _16;
    end
    assign _135 = ~ g2_rp;
    assign _136 = _131 ? _135 : g2_rp;
    assign _17 = _136;
    always @(posedge aclk) begin
        if (rst)
            g2_rp <= _106;
        else
            g2_rp <= _17;
    end
    assign _137 = g2_rp ? g2_e1 : g2_e0;
    assign _192 = 2'b10;
    assign _148 = 2'b01;
    assign _149 = g0_cnt + _148;
    assign _146 = g0_cnt - _148;
    assign _143 = 2'b00;
    assign _20 = _150;
    always @(posedge aclk) begin
        if (rst)
            g0_cnt <= _143;
        else
            g0_cnt <= _20;
    end
    assign _140 = ~ _104;
    assign _141 = _140 & _114;
    assign _147 = _141 ? _146 : g0_cnt;
    assign _162 = g1_cnt + _148;
    assign _159 = g1_cnt - _148;
    assign _21 = _163;
    always @(posedge aclk) begin
        if (rst)
            g1_cnt <= _143;
        else
            g1_cnt <= _21;
    end
    assign _153 = ~ _85;
    assign _154 = _153 & _121;
    assign _160 = _154 ? _159 : g1_cnt;
    assign _175 = g2_cnt + _148;
    assign _172 = g2_cnt - _148;
    assign _22 = _176;
    always @(posedge aclk) begin
        if (rst)
            g2_cnt <= _143;
        else
            g2_cnt <= _22;
    end
    assign _166 = ~ _60;
    assign _167 = _166 & _131;
    assign _173 = _167 ? _172 : g2_cnt;
    assign _178 = _176 == _143;
    assign _179 = ~ _178;
    assign _24 = _179;
    always @(posedge aclk) begin
        if (rst)
            g2_m_valid <= _106;
        else
            g2_m_valid <= _24;
    end
    assign _131 = g2_m_valid & m_axis_tready;
    assign _164 = ~ _131;
    assign _60 = g1_m_valid & g2_s_ready;
    assign _165 = _60 & _164;
    assign _176 = _165 ? _175 : _173;
    assign _181 = _176 == _192;
    assign _182 = ~ _181;
    assign _25 = _182;
    always @(posedge aclk) begin
        if (rst)
            g2_s_ready <= _106;
        else
            g2_s_ready <= _25;
    end
    assign _26 = g2_s_ready;
    assign _184 = _163 == _143;
    assign _185 = ~ _184;
    assign _27 = _185;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _106;
        else
            g1_m_valid <= _27;
    end
    assign _121 = g1_m_valid & _26;
    assign _151 = ~ _121;
    assign _85 = g0_m_valid & g1_s_ready;
    assign _152 = _85 & _151;
    assign _163 = _152 ? _162 : _160;
    assign _187 = _163 == _192;
    assign _188 = ~ _187;
    assign _28 = _188;
    always @(posedge aclk) begin
        if (rst)
            g1_s_ready <= _106;
        else
            g1_s_ready <= _28;
    end
    assign _29 = g1_s_ready;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _190 = _150 == _143;
    assign _191 = ~ _190;
    assign _32 = _191;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _106;
        else
            g0_m_valid <= _32;
    end
    assign _114 = g0_m_valid & _29;
    assign _138 = ~ _114;
    assign _104 = s_axis_tvalid & g0_s_ready;
    assign _139 = _104 & _138;
    assign _150 = _139 ? _149 : _147;
    assign _193 = _150 == _192;
    assign _194 = ~ _193;
    assign _34 = _194;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _106;
        else
            g0_s_ready <= _34;
    end
    assign _35 = g0_s_ready;
    assign s_axis_tready = _35;
    assign m_axis_tvalid = g2_m_valid;
    assign m_axis_tdata = _137;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n1_m3_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _25;
    wire [3:0] _20;
    wire [3:0] _27;
    wire [3:0] _28;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _31;
    wire [3:0] _34;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _38;
    wire [3:0] _42;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire _36;
    wire _47;
    wire vdd;
    wire rst;
    wire _12;
    reg g0_m_valid;
    wire _44;
    wire _46;
    wire _43;
    wire _48;
    wire _14;
    wire _49;
    wire _15;
    reg g0_s_ready;
    wire _16;
    assign _25 = g0_m_valid & m_axis_tready;
    assign _20 = 4'b0000;
    assign _27 = 4'b0001;
    assign _28 = f_out + _27;
    assign _1 = _28;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _20;
        else
            if (_25)
                f_out <= _1;
    end
    assign _31 = s_axis_tvalid & _16;
    assign _34 = f_in + _27;
    assign _3 = _34;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _20;
        else
            if (_31)
                f_in <= _3;
    end
    assign _38 = g0_s_ready & s_axis_tvalid;
    assign _42 = _38 ? s_axis_tdata : g0_m_data;
    assign _6 = _42;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign _36 = 1'b0;
    assign _47 = 1'b1;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _12 = _14;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _36;
        else
            g0_m_valid <= _12;
    end
    assign _44 = g0_m_valid & m_axis_tready;
    assign _46 = _44 ? _36 : g0_m_valid;
    assign _43 = g0_s_ready & s_axis_tvalid;
    assign _48 = _43 ? _47 : _46;
    assign _14 = _48;
    assign _49 = ~ _14;
    assign _15 = _49;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _36;
        else
            g0_s_ready <= _15;
    end
    assign _16 = g0_s_ready;
    assign s_axis_tready = _16;
    assign m_axis_tvalid = g0_m_valid;
    assign m_axis_tdata = g0_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n2_m3_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _30;
    wire [3:0] _25;
    wire [3:0] _32;
    wire [3:0] _33;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _36;
    wire [3:0] _39;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _43;
    wire [3:0] _47;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire _54;
    wire [3:0] _58;
    wire [3:0] _7;
    reg [3:0] g1_m_data;
    wire _41;
    wire _70;
    wire _11;
    reg g1_m_valid;
    wire _60;
    wire _62;
    wire _59;
    wire _64;
    wire _12;
    wire _65;
    wire _13;
    reg g1_s_ready;
    wire _14;
    wire vdd;
    wire rst;
    wire _17;
    reg g0_m_valid;
    wire _67;
    wire _69;
    wire _66;
    wire _71;
    wire _19;
    wire _72;
    wire _20;
    reg g0_s_ready;
    wire _21;
    assign _30 = g1_m_valid & m_axis_tready;
    assign _25 = 4'b0000;
    assign _32 = 4'b0001;
    assign _33 = f_out + _32;
    assign _1 = _33;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _25;
        else
            if (_30)
                f_out <= _1;
    end
    assign _36 = s_axis_tvalid & _21;
    assign _39 = f_in + _32;
    assign _3 = _39;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _25;
        else
            if (_36)
                f_in <= _3;
    end
    assign _43 = g0_s_ready & s_axis_tvalid;
    assign _47 = _43 ? s_axis_tdata : g0_m_data;
    assign _6 = _47;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign _54 = g1_s_ready & g0_m_valid;
    assign _58 = _54 ? g0_m_data : g1_m_data;
    assign _7 = _58;
    always @(posedge aclk) begin
        g1_m_data <= _7;
    end
    assign _41 = 1'b0;
    assign _70 = 1'b1;
    assign _11 = _12;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _41;
        else
            g1_m_valid <= _11;
    end
    assign _60 = g1_m_valid & m_axis_tready;
    assign _62 = _60 ? _41 : g1_m_valid;
    assign _59 = g1_s_ready & g0_m_valid;
    assign _64 = _59 ? _70 : _62;
    assign _12 = _64;
    assign _65 = ~ _12;
    assign _13 = _65;
    always @(posedge aclk) begin
        if (rst)
            g1_s_ready <= _41;
        else
            g1_s_ready <= _13;
    end
    assign _14 = g1_s_ready;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _17 = _19;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _41;
        else
            g0_m_valid <= _17;
    end
    assign _67 = g0_m_valid & _14;
    assign _69 = _67 ? _41 : g0_m_valid;
    assign _66 = g0_s_ready & s_axis_tvalid;
    assign _71 = _66 ? _70 : _69;
    assign _19 = _71;
    assign _72 = ~ _19;
    assign _20 = _72;
    always @(posedge aclk) begin
        if (rst)
            g0_s_ready <= _41;
        else
            g0_s_ready <= _20;
    end
    assign _21 = g0_s_ready;
    assign s_axis_tready = _21;
    assign m_axis_tvalid = g1_m_valid;
    assign m_axis_tdata = g1_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n1_m4_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _23;
    wire [3:0] _18;
    wire [3:0] _25;
    wire [3:0] _26;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _29;
    wire [3:0] _32;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _35;
    wire [3:0] _39;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire vdd;
    wire _20;
    wire rst;
    wire _40;
    wire _13;
    reg g0_m_valid;
    wire _33;
    wire _34;
    wire _14;
    assign _23 = g0_m_valid & m_axis_tready;
    assign _18 = 4'b0000;
    assign _25 = 4'b0001;
    assign _26 = f_out + _25;
    assign _1 = _26;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _18;
        else
            if (_23)
                f_out <= _1;
    end
    assign _29 = s_axis_tvalid & _14;
    assign _32 = f_in + _25;
    assign _3 = _32;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _18;
        else
            if (_29)
                f_in <= _3;
    end
    assign _35 = _34 & s_axis_tvalid;
    assign _39 = _35 ? s_axis_tdata : g0_m_data;
    assign _6 = _39;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign vdd = 1'b1;
    assign _20 = 1'b0;
    assign rst = ~ aresetn;
    assign _40 = _34 ? s_axis_tvalid : g0_m_valid;
    assign _13 = _40;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _20;
        else
            g0_m_valid <= _13;
    end
    assign _33 = ~ g0_m_valid;
    assign _34 = _33 | m_axis_tready;
    assign _14 = _34;
    assign s_axis_tready = _14;
    assign m_axis_tvalid = g0_m_valid;
    assign m_axis_tdata = g0_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n2_m4_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _26;
    wire [3:0] _21;
    wire [3:0] _28;
    wire [3:0] _29;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _32;
    wire [3:0] _35;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _41;
    wire [3:0] _45;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire _48;
    wire [3:0] _52;
    wire [3:0] _7;
    reg [3:0] g1_m_data;
    wire _23;
    wire _53;
    wire _11;
    reg g1_m_valid;
    wire _46;
    wire _47;
    wire _12;
    wire vdd;
    wire rst;
    wire _54;
    wire _16;
    reg g0_m_valid;
    wire _39;
    wire _40;
    wire _17;
    assign _26 = g1_m_valid & m_axis_tready;
    assign _21 = 4'b0000;
    assign _28 = 4'b0001;
    assign _29 = f_out + _28;
    assign _1 = _29;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _21;
        else
            if (_26)
                f_out <= _1;
    end
    assign _32 = s_axis_tvalid & _17;
    assign _35 = f_in + _28;
    assign _3 = _35;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _21;
        else
            if (_32)
                f_in <= _3;
    end
    assign _41 = _40 & s_axis_tvalid;
    assign _45 = _41 ? s_axis_tdata : g0_m_data;
    assign _6 = _45;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign _48 = _47 & g0_m_valid;
    assign _52 = _48 ? g0_m_data : g1_m_data;
    assign _7 = _52;
    always @(posedge aclk) begin
        g1_m_data <= _7;
    end
    assign _23 = 1'b0;
    assign _53 = _47 ? g0_m_valid : g1_m_valid;
    assign _11 = _53;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _23;
        else
            g1_m_valid <= _11;
    end
    assign _46 = ~ g1_m_valid;
    assign _47 = _46 | m_axis_tready;
    assign _12 = _47;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _54 = _40 ? s_axis_tvalid : g0_m_valid;
    assign _16 = _54;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _23;
        else
            g0_m_valid <= _16;
    end
    assign _39 = ~ g0_m_valid;
    assign _40 = _39 | _12;
    assign _17 = _40;
    assign s_axis_tready = _17;
    assign m_axis_tvalid = g1_m_valid;
    assign m_axis_tdata = g1_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n3_m4_000 (
    s_axis_tdata,
    m_axis_tready,
    aresetn,
    aclk,
    s_axis_tvalid,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input [3:0] s_axis_tdata;
    input m_axis_tready;
    input aresetn;
    input aclk;
    input s_axis_tvalid;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _29;
    wire [3:0] _24;
    wire [3:0] _31;
    wire [3:0] _32;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _35;
    wire [3:0] _38;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _44;
    wire [3:0] _48;
    wire [3:0] _6;
    reg [3:0] g0_m_data;
    wire _54;
    wire [3:0] _58;
    wire [3:0] _7;
    reg [3:0] g1_m_data;
    wire _61;
    wire [3:0] _65;
    wire [3:0] _8;
    reg [3:0] g2_m_data;
    wire _26;
    wire _66;
    wire _12;
    reg g2_m_valid;
    wire _59;
    wire _60;
    wire _13;
    wire _67;
    wire _14;
    reg g1_m_valid;
    wire _52;
    wire _53;
    wire _15;
    wire vdd;
    wire rst;
    wire _68;
    wire _19;
    reg g0_m_valid;
    wire _42;
    wire _43;
    wire _20;
    assign _29 = g2_m_valid & m_axis_tready;
    assign _24 = 4'b0000;
    assign _31 = 4'b0001;
    assign _32 = f_out + _31;
    assign _1 = _32;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _24;
        else
            if (_29)
                f_out <= _1;
    end
    assign _35 = s_axis_tvalid & _20;
    assign _38 = f_in + _31;
    assign _3 = _38;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _24;
        else
            if (_35)
                f_in <= _3;
    end
    assign _44 = _43 & s_axis_tvalid;
    assign _48 = _44 ? s_axis_tdata : g0_m_data;
    assign _6 = _48;
    always @(posedge aclk) begin
        g0_m_data <= _6;
    end
    assign _54 = _53 & g0_m_valid;
    assign _58 = _54 ? g0_m_data : g1_m_data;
    assign _7 = _58;
    always @(posedge aclk) begin
        g1_m_data <= _7;
    end
    assign _61 = _60 & g1_m_valid;
    assign _65 = _61 ? g1_m_data : g2_m_data;
    assign _8 = _65;
    always @(posedge aclk) begin
        g2_m_data <= _8;
    end
    assign _26 = 1'b0;
    assign _66 = _60 ? g1_m_valid : g2_m_valid;
    assign _12 = _66;
    always @(posedge aclk) begin
        if (rst)
            g2_m_valid <= _26;
        else
            g2_m_valid <= _12;
    end
    assign _59 = ~ g2_m_valid;
    assign _60 = _59 | m_axis_tready;
    assign _13 = _60;
    assign _67 = _53 ? g0_m_valid : g1_m_valid;
    assign _14 = _67;
    always @(posedge aclk) begin
        if (rst)
            g1_m_valid <= _26;
        else
            g1_m_valid <= _14;
    end
    assign _52 = ~ g1_m_valid;
    assign _53 = _52 | _13;
    assign _15 = _53;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _68 = _43 ? s_axis_tvalid : g0_m_valid;
    assign _19 = _68;
    always @(posedge aclk) begin
        if (rst)
            g0_m_valid <= _26;
        else
            g0_m_valid <= _19;
    end
    assign _42 = ~ g0_m_valid;
    assign _43 = _42 | _15;
    assign _20 = _43;
    assign s_axis_tready = _20;
    assign m_axis_tvalid = g2_m_valid;
    assign m_axis_tdata = g2_m_data;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module pipe_reg_hc_w4_n0_m1_000 (
    aresetn,
    aclk,
    s_axis_tdata,
    s_axis_tvalid,
    m_axis_tready,
    s_axis_tready,
    m_axis_tvalid,
    m_axis_tdata,
    f_in_o,
    f_out_o
);

    input aresetn;
    input aclk;
    input [3:0] s_axis_tdata;
    input s_axis_tvalid;
    input m_axis_tready;
    output s_axis_tready;
    output m_axis_tvalid;
    output [3:0] m_axis_tdata;
    output [3:0] f_in_o;
    output [3:0] f_out_o;

    wire _16;
    wire [3:0] _15;
    wire [3:0] _18;
    wire [3:0] _19;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire _22;
    wire rst;
    wire [3:0] _25;
    wire [3:0] _5;
    reg [3:0] f_in;
    assign _16 = s_axis_tvalid & m_axis_tready;
    assign _15 = 4'b0000;
    assign _18 = 4'b0001;
    assign _19 = f_out + _18;
    assign _1 = _19;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _15;
        else
            if (_16)
                f_out <= _1;
    end
    assign _22 = s_axis_tvalid & m_axis_tready;
    assign rst = ~ aresetn;
    assign _25 = f_in + _18;
    assign _5 = _25;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _15;
        else
            if (_22)
                f_in <= _5;
    end
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tvalid = s_axis_tvalid;
    assign m_axis_tdata = s_axis_tdata;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

// pipe_reg: wrapper generated by gen.exe (brief 171). Same parameters and ports as ip_lib/pipe_reg/rtl/pipe_reg.sv;
// the datapath is the Hardcaml module of the matching parameter point.
module pipe_reg #(
    parameter int W        = 32,
    parameter int N        = 1,
    parameter int MODE     = 1,
    parameter int TLAST_EN = 0,
    parameter int TKEEP_EN = 0,
    parameter int TUSER_W  = 0
) (
    input  logic                         aclk,
    input  logic                         aresetn,
    input  logic                         s_axis_tvalid,
    output logic                         s_axis_tready,
    input  logic [W-1:0]                 s_axis_tdata,
    input  logic                         s_axis_tlast,
    input  logic [(W/8 > 0 ? W/8 : 1)-1:0] s_axis_tkeep,
    input  logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] s_axis_tuser,
    output logic                         m_axis_tvalid,
    input  logic                         m_axis_tready,
    output logic [W-1:0]                 m_axis_tdata,
    output logic                         m_axis_tlast,
    output logic [(W/8 > 0 ? W/8 : 1)-1:0] m_axis_tkeep,
    output logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] m_axis_tuser,
    output logic [W-1:0] f_in_o, f_out_o
);
    generate
        if (W == 4 && N == 1 && MODE == 0 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n1_m0_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 3 && MODE == 0 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n3_m0_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 1 && MODE == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n1_m1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 2 && MODE == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n2_m1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 3 && MODE == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n3_m1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 1 && MODE == 2 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n1_m2_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 2 && MODE == 2 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n2_m2_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 3 && MODE == 2 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n3_m2_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 1 && MODE == 3 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n1_m3_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 2 && MODE == 3 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n2_m3_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 1 && MODE == 4 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n1_m4_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 2 && MODE == 4 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n2_m4_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 3 && MODE == 4 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n3_m4_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && N == 0 && MODE == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            pipe_reg_hc_w4_n0_m1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end
    endgenerate
endmodule
