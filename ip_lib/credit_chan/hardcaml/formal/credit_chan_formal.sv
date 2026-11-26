module credit_chan_hc_w4_c1_f0_b0_000 (
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

    wire [3:0] _21;
    wire [3:0] _28;
    wire [3:0] _29;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _38;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _40;
    wire _44;
    wire _45;
    wire _43;
    wire _47;
    wire _48;
    wire _6;
    reg wp;
    reg [3:0] _59[0:0];
    wire _55;
    wire _53;
    wire _57;
    wire _58;
    wire _7;
    reg rp;
    wire [3:0] fifo_head;
    wire _72;
    wire _69;
    wire _10;
    reg credits;
    wire _63;
    wire _64;
    wire _70;
    wire _85;
    wire _82;
    wire vdd;
    wire rst;
    wire _14;
    reg cnt;
    wire _76;
    wire _77;
    wire _83;
    wire _74;
    wire _75;
    wire _86;
    wire _88;
    wire _89;
    wire _15;
    reg m_valid_q;
    wire _26;
    wire _61;
    wire _35;
    wire _62;
    wire _73;
    wire _91;
    wire _92;
    wire _17;
    reg s_ready_q;
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
    assign _38 = f_in + _28;
    assign _3 = _38;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _21;
        else
            if (_35)
                f_in <= _3;
    end
    assign _40 = 1'b0;
    assign _44 = 1'b1;
    assign _45 = wp + _44;
    assign _43 = wp == _40;
    assign _47 = _43 ? _40 : _45;
    assign _48 = _35 ? _47 : wp;
    assign _6 = _48;
    always @(posedge aclk) begin
        if (rst)
            wp <= _40;
        else
            wp <= _6;
    end
    always @(posedge aclk) begin
        if (_35)
            _59[wp] <= s_axis_tdata;
    end
    assign _55 = rp + _44;
    assign _53 = rp == _40;
    assign _57 = _53 ? _40 : _55;
    assign _58 = _26 ? _57 : rp;
    assign _7 = _58;
    always @(posedge aclk) begin
        if (rst)
            rp <= _40;
        else
            rp <= _7;
    end
    assign fifo_head = _59[rp];
    assign _72 = credits - _44;
    assign _69 = credits + _44;
    assign _10 = _73;
    always @(posedge aclk) begin
        if (rst)
            credits <= _44;
        else
            credits <= _10;
    end
    assign _63 = ~ _35;
    assign _64 = _63 & _26;
    assign _70 = _64 ? _69 : credits;
    assign _85 = cnt + _44;
    assign _82 = cnt - _44;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _14 = _86;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _40;
        else
            cnt <= _14;
    end
    assign _76 = ~ _35;
    assign _77 = _76 & _26;
    assign _83 = _77 ? _82 : cnt;
    assign _74 = ~ _26;
    assign _75 = _35 & _74;
    assign _86 = _75 ? _85 : _83;
    assign _88 = _86 == _40;
    assign _89 = ~ _88;
    assign _15 = _89;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _40;
        else
            m_valid_q <= _15;
    end
    assign _26 = m_valid_q & m_axis_tready;
    assign _61 = ~ _26;
    assign _35 = s_axis_tvalid & s_ready_q;
    assign _62 = _35 & _61;
    assign _73 = _62 ? _72 : _70;
    assign _91 = _73 == _40;
    assign _92 = ~ _91;
    assign _17 = _92;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _40;
        else
            s_ready_q <= _17;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c2_f0_b0_000 (
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

    wire [3:0] _21;
    wire [3:0] _28;
    wire [3:0] _29;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _38;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire _40;
    wire _44;
    wire _45;
    wire _43;
    wire _47;
    wire _48;
    wire _6;
    reg wp;
    reg [3:0] _59[0:1];
    wire _55;
    wire _53;
    wire _57;
    wire _58;
    wire _7;
    reg rp;
    wire [3:0] fifo_head;
    wire [1:0] _90;
    wire [1:0] _71;
    wire [1:0] _72;
    wire [1:0] _69;
    wire [1:0] _66;
    wire [1:0] _10;
    reg [1:0] credits;
    wire _63;
    wire _64;
    wire [1:0] _70;
    wire [1:0] _85;
    wire [1:0] _82;
    wire vdd;
    wire rst;
    wire [1:0] _14;
    reg [1:0] cnt;
    wire _76;
    wire _77;
    wire [1:0] _83;
    wire _74;
    wire _75;
    wire [1:0] _86;
    wire _88;
    wire _89;
    wire _15;
    reg m_valid_q;
    wire _26;
    wire _61;
    wire _35;
    wire _62;
    wire [1:0] _73;
    wire _91;
    wire _92;
    wire _17;
    reg s_ready_q;
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
    assign _38 = f_in + _28;
    assign _3 = _38;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _21;
        else
            if (_35)
                f_in <= _3;
    end
    assign _40 = 1'b0;
    assign _44 = 1'b1;
    assign _45 = wp + _44;
    assign _43 = wp == _44;
    assign _47 = _43 ? _40 : _45;
    assign _48 = _35 ? _47 : wp;
    assign _6 = _48;
    always @(posedge aclk) begin
        if (rst)
            wp <= _40;
        else
            wp <= _6;
    end
    always @(posedge aclk) begin
        if (_35)
            _59[wp] <= s_axis_tdata;
    end
    assign _55 = rp + _44;
    assign _53 = rp == _44;
    assign _57 = _53 ? _40 : _55;
    assign _58 = _26 ? _57 : rp;
    assign _7 = _58;
    always @(posedge aclk) begin
        if (rst)
            rp <= _40;
        else
            rp <= _7;
    end
    assign fifo_head = _59[rp];
    assign _90 = 2'b00;
    assign _71 = 2'b01;
    assign _72 = credits - _71;
    assign _69 = credits + _71;
    assign _66 = 2'b10;
    assign _10 = _73;
    always @(posedge aclk) begin
        if (rst)
            credits <= _66;
        else
            credits <= _10;
    end
    assign _63 = ~ _35;
    assign _64 = _63 & _26;
    assign _70 = _64 ? _69 : credits;
    assign _85 = cnt + _71;
    assign _82 = cnt - _71;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _14 = _86;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _90;
        else
            cnt <= _14;
    end
    assign _76 = ~ _35;
    assign _77 = _76 & _26;
    assign _83 = _77 ? _82 : cnt;
    assign _74 = ~ _26;
    assign _75 = _35 & _74;
    assign _86 = _75 ? _85 : _83;
    assign _88 = _86 == _90;
    assign _89 = ~ _88;
    assign _15 = _89;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _40;
        else
            m_valid_q <= _15;
    end
    assign _26 = m_valid_q & m_axis_tready;
    assign _61 = ~ _26;
    assign _35 = s_axis_tvalid & s_ready_q;
    assign _62 = _35 & _61;
    assign _73 = _62 ? _72 : _70;
    assign _91 = _73 == _90;
    assign _92 = ~ _91;
    assign _17 = _92;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _40;
        else
            s_ready_q <= _17;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c1_f1_b1_000 (
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

    wire [3:0] _24;
    wire [3:0] _31;
    wire [3:0] _32;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _41;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire _46;
    wire _50;
    wire _51;
    wire _49;
    wire _53;
    wire _54;
    wire _7;
    reg wp;
    reg [3:0] _68[0:0];
    wire _61;
    wire _59;
    wire _63;
    wire _64;
    wire _8;
    reg rp;
    wire [3:0] fifo_head;
    wire _84;
    wire _81;
    wire _11;
    reg credits;
    wire _75;
    wire _76;
    wire _82;
    wire _97;
    wire _94;
    wire _13;
    reg cnt;
    wire _88;
    wire _89;
    wire _95;
    wire _86;
    wire vdd;
    wire rst;
    wire _16;
    reg fwd1_valid;
    wire _87;
    wire _98;
    wire _100;
    wire _101;
    wire _17;
    reg m_valid_q;
    wire _29;
    wire _18;
    reg back1_credit;
    wire _73;
    wire _38;
    wire _74;
    wire _85;
    wire _103;
    wire _104;
    wire _20;
    reg s_ready_q;
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
    assign _41 = f_in + _31;
    assign _3 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _24;
        else
            if (_38)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _46 = 1'b0;
    assign _50 = 1'b1;
    assign _51 = wp + _50;
    assign _49 = wp == _46;
    assign _53 = _49 ? _46 : _51;
    assign _54 = fwd1_valid ? _53 : wp;
    assign _7 = _54;
    always @(posedge aclk) begin
        if (rst)
            wp <= _46;
        else
            wp <= _7;
    end
    always @(posedge aclk) begin
        if (fwd1_valid)
            _68[wp] <= fwd1_data;
    end
    assign _61 = rp + _50;
    assign _59 = rp == _46;
    assign _63 = _59 ? _46 : _61;
    assign _64 = _29 ? _63 : rp;
    assign _8 = _64;
    always @(posedge aclk) begin
        if (rst)
            rp <= _46;
        else
            rp <= _8;
    end
    assign fifo_head = _68[rp];
    assign _84 = credits - _50;
    assign _81 = credits + _50;
    assign _11 = _85;
    always @(posedge aclk) begin
        if (rst)
            credits <= _50;
        else
            credits <= _11;
    end
    assign _75 = ~ _38;
    assign _76 = _75 & back1_credit;
    assign _82 = _76 ? _81 : credits;
    assign _97 = cnt + _50;
    assign _94 = cnt - _50;
    assign _13 = _98;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _46;
        else
            cnt <= _13;
    end
    assign _88 = ~ fwd1_valid;
    assign _89 = _88 & _29;
    assign _95 = _89 ? _94 : cnt;
    assign _86 = ~ _29;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _16 = _38;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _46;
        else
            fwd1_valid <= _16;
    end
    assign _87 = fwd1_valid & _86;
    assign _98 = _87 ? _97 : _95;
    assign _100 = _98 == _46;
    assign _101 = ~ _100;
    assign _17 = _101;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _46;
        else
            m_valid_q <= _17;
    end
    assign _29 = m_valid_q & m_axis_tready;
    assign _18 = _29;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _46;
        else
            back1_credit <= _18;
    end
    assign _73 = ~ back1_credit;
    assign _38 = s_axis_tvalid & s_ready_q;
    assign _74 = _38 & _73;
    assign _85 = _74 ? _84 : _82;
    assign _103 = _85 == _46;
    assign _104 = ~ _103;
    assign _20 = _104;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _46;
        else
            s_ready_q <= _20;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c2_f1_b1_000 (
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

    wire [3:0] _24;
    wire [3:0] _31;
    wire [3:0] _32;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _41;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire _46;
    wire _50;
    wire _51;
    wire _49;
    wire _53;
    wire _54;
    wire _7;
    reg wp;
    reg [3:0] _68[0:1];
    wire _61;
    wire _59;
    wire _63;
    wire _64;
    wire _8;
    reg rp;
    wire [3:0] fifo_head;
    wire [1:0] _102;
    wire [1:0] _83;
    wire [1:0] _84;
    wire [1:0] _81;
    wire [1:0] _78;
    wire [1:0] _11;
    reg [1:0] credits;
    wire _75;
    wire _76;
    wire [1:0] _82;
    wire [1:0] _97;
    wire [1:0] _94;
    wire [1:0] _13;
    reg [1:0] cnt;
    wire _88;
    wire _89;
    wire [1:0] _95;
    wire _86;
    wire vdd;
    wire rst;
    wire _16;
    reg fwd1_valid;
    wire _87;
    wire [1:0] _98;
    wire _100;
    wire _101;
    wire _17;
    reg m_valid_q;
    wire _29;
    wire _18;
    reg back1_credit;
    wire _73;
    wire _38;
    wire _74;
    wire [1:0] _85;
    wire _103;
    wire _104;
    wire _20;
    reg s_ready_q;
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
    assign _41 = f_in + _31;
    assign _3 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _24;
        else
            if (_38)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _46 = 1'b0;
    assign _50 = 1'b1;
    assign _51 = wp + _50;
    assign _49 = wp == _50;
    assign _53 = _49 ? _46 : _51;
    assign _54 = fwd1_valid ? _53 : wp;
    assign _7 = _54;
    always @(posedge aclk) begin
        if (rst)
            wp <= _46;
        else
            wp <= _7;
    end
    always @(posedge aclk) begin
        if (fwd1_valid)
            _68[wp] <= fwd1_data;
    end
    assign _61 = rp + _50;
    assign _59 = rp == _50;
    assign _63 = _59 ? _46 : _61;
    assign _64 = _29 ? _63 : rp;
    assign _8 = _64;
    always @(posedge aclk) begin
        if (rst)
            rp <= _46;
        else
            rp <= _8;
    end
    assign fifo_head = _68[rp];
    assign _102 = 2'b00;
    assign _83 = 2'b01;
    assign _84 = credits - _83;
    assign _81 = credits + _83;
    assign _78 = 2'b10;
    assign _11 = _85;
    always @(posedge aclk) begin
        if (rst)
            credits <= _78;
        else
            credits <= _11;
    end
    assign _75 = ~ _38;
    assign _76 = _75 & back1_credit;
    assign _82 = _76 ? _81 : credits;
    assign _97 = cnt + _83;
    assign _94 = cnt - _83;
    assign _13 = _98;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _102;
        else
            cnt <= _13;
    end
    assign _88 = ~ fwd1_valid;
    assign _89 = _88 & _29;
    assign _95 = _89 ? _94 : cnt;
    assign _86 = ~ _29;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _16 = _38;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _46;
        else
            fwd1_valid <= _16;
    end
    assign _87 = fwd1_valid & _86;
    assign _98 = _87 ? _97 : _95;
    assign _100 = _98 == _102;
    assign _101 = ~ _100;
    assign _17 = _101;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _46;
        else
            m_valid_q <= _17;
    end
    assign _29 = m_valid_q & m_axis_tready;
    assign _18 = _29;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _46;
        else
            back1_credit <= _18;
    end
    assign _73 = ~ back1_credit;
    assign _38 = s_axis_tvalid & s_ready_q;
    assign _74 = _38 & _73;
    assign _85 = _74 ? _84 : _82;
    assign _103 = _85 == _102;
    assign _104 = ~ _103;
    assign _20 = _104;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _46;
        else
            s_ready_q <= _20;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c3_f1_b1_000 (
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

    wire [3:0] _24;
    wire [3:0] _31;
    wire [3:0] _32;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _41;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire [1:0] _46;
    wire [1:0] _50;
    wire [1:0] _51;
    wire [1:0] _48;
    wire _49;
    wire [1:0] _53;
    wire [1:0] _54;
    wire [1:0] _7;
    reg [1:0] wp;
    reg [3:0] _68[0:2];
    wire [1:0] _61;
    wire _59;
    wire [1:0] _63;
    wire [1:0] _64;
    wire [1:0] _8;
    reg [1:0] rp;
    wire [3:0] fifo_head;
    wire _36;
    wire [1:0] _84;
    wire [1:0] _81;
    wire [1:0] _78;
    wire [1:0] _11;
    reg [1:0] credits;
    wire _75;
    wire _76;
    wire [1:0] _82;
    wire [1:0] _97;
    wire [1:0] _94;
    wire [1:0] _13;
    reg [1:0] cnt;
    wire _88;
    wire _89;
    wire [1:0] _95;
    wire _86;
    wire vdd;
    wire rst;
    wire _16;
    reg fwd1_valid;
    wire _87;
    wire [1:0] _98;
    wire _100;
    wire _101;
    wire _17;
    reg m_valid_q;
    wire _29;
    wire _18;
    reg back1_credit;
    wire _73;
    wire _38;
    wire _74;
    wire [1:0] _85;
    wire _103;
    wire _104;
    wire _20;
    reg s_ready_q;
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
    assign _41 = f_in + _31;
    assign _3 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _24;
        else
            if (_38)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _46 = 2'b00;
    assign _50 = 2'b01;
    assign _51 = wp + _50;
    assign _48 = 2'b10;
    assign _49 = wp == _48;
    assign _53 = _49 ? _46 : _51;
    assign _54 = fwd1_valid ? _53 : wp;
    assign _7 = _54;
    always @(posedge aclk) begin
        if (rst)
            wp <= _46;
        else
            wp <= _7;
    end
    always @(posedge aclk) begin
        if (fwd1_valid)
            _68[wp] <= fwd1_data;
    end
    assign _61 = rp + _50;
    assign _59 = rp == _48;
    assign _63 = _59 ? _46 : _61;
    assign _64 = _29 ? _63 : rp;
    assign _8 = _64;
    always @(posedge aclk) begin
        if (rst)
            rp <= _46;
        else
            rp <= _8;
    end
    assign fifo_head = _68[rp];
    assign _36 = 1'b0;
    assign _84 = credits - _50;
    assign _81 = credits + _50;
    assign _78 = 2'b11;
    assign _11 = _85;
    always @(posedge aclk) begin
        if (rst)
            credits <= _78;
        else
            credits <= _11;
    end
    assign _75 = ~ _38;
    assign _76 = _75 & back1_credit;
    assign _82 = _76 ? _81 : credits;
    assign _97 = cnt + _50;
    assign _94 = cnt - _50;
    assign _13 = _98;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _46;
        else
            cnt <= _13;
    end
    assign _88 = ~ fwd1_valid;
    assign _89 = _88 & _29;
    assign _95 = _89 ? _94 : cnt;
    assign _86 = ~ _29;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _16 = _38;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _36;
        else
            fwd1_valid <= _16;
    end
    assign _87 = fwd1_valid & _86;
    assign _98 = _87 ? _97 : _95;
    assign _100 = _98 == _46;
    assign _101 = ~ _100;
    assign _17 = _101;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _36;
        else
            m_valid_q <= _17;
    end
    assign _29 = m_valid_q & m_axis_tready;
    assign _18 = _29;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _36;
        else
            back1_credit <= _18;
    end
    assign _73 = ~ back1_credit;
    assign _38 = s_axis_tvalid & s_ready_q;
    assign _74 = _38 & _73;
    assign _85 = _74 ? _84 : _82;
    assign _103 = _85 == _46;
    assign _104 = ~ _103;
    assign _20 = _104;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _36;
        else
            s_ready_q <= _20;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c4_f1_b1_000 (
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

    wire [3:0] _24;
    wire [3:0] _31;
    wire [3:0] _32;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _41;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire [1:0] _46;
    wire [1:0] _50;
    wire [1:0] _51;
    wire [1:0] _48;
    wire _49;
    wire [1:0] _53;
    wire [1:0] _54;
    wire [1:0] _7;
    reg [1:0] wp;
    reg [3:0] _68[0:3];
    wire [1:0] _61;
    wire _59;
    wire [1:0] _63;
    wire [1:0] _64;
    wire [1:0] _8;
    reg [1:0] rp;
    wire [3:0] fifo_head;
    wire _36;
    wire [2:0] _102;
    wire [2:0] _83;
    wire [2:0] _84;
    wire [2:0] _81;
    wire [2:0] _78;
    wire [2:0] _11;
    reg [2:0] credits;
    wire _75;
    wire _76;
    wire [2:0] _82;
    wire [2:0] _97;
    wire [2:0] _94;
    wire [2:0] _13;
    reg [2:0] cnt;
    wire _88;
    wire _89;
    wire [2:0] _95;
    wire _86;
    wire vdd;
    wire rst;
    wire _16;
    reg fwd1_valid;
    wire _87;
    wire [2:0] _98;
    wire _100;
    wire _101;
    wire _17;
    reg m_valid_q;
    wire _29;
    wire _18;
    reg back1_credit;
    wire _73;
    wire _38;
    wire _74;
    wire [2:0] _85;
    wire _103;
    wire _104;
    wire _20;
    reg s_ready_q;
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
    assign _41 = f_in + _31;
    assign _3 = _41;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _24;
        else
            if (_38)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _46 = 2'b00;
    assign _50 = 2'b01;
    assign _51 = wp + _50;
    assign _48 = 2'b11;
    assign _49 = wp == _48;
    assign _53 = _49 ? _46 : _51;
    assign _54 = fwd1_valid ? _53 : wp;
    assign _7 = _54;
    always @(posedge aclk) begin
        if (rst)
            wp <= _46;
        else
            wp <= _7;
    end
    always @(posedge aclk) begin
        if (fwd1_valid)
            _68[wp] <= fwd1_data;
    end
    assign _61 = rp + _50;
    assign _59 = rp == _48;
    assign _63 = _59 ? _46 : _61;
    assign _64 = _29 ? _63 : rp;
    assign _8 = _64;
    always @(posedge aclk) begin
        if (rst)
            rp <= _46;
        else
            rp <= _8;
    end
    assign fifo_head = _68[rp];
    assign _36 = 1'b0;
    assign _102 = 3'b000;
    assign _83 = 3'b001;
    assign _84 = credits - _83;
    assign _81 = credits + _83;
    assign _78 = 3'b100;
    assign _11 = _85;
    always @(posedge aclk) begin
        if (rst)
            credits <= _78;
        else
            credits <= _11;
    end
    assign _75 = ~ _38;
    assign _76 = _75 & back1_credit;
    assign _82 = _76 ? _81 : credits;
    assign _97 = cnt + _83;
    assign _94 = cnt - _83;
    assign _13 = _98;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _102;
        else
            cnt <= _13;
    end
    assign _88 = ~ fwd1_valid;
    assign _89 = _88 & _29;
    assign _95 = _89 ? _94 : cnt;
    assign _86 = ~ _29;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _16 = _38;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _36;
        else
            fwd1_valid <= _16;
    end
    assign _87 = fwd1_valid & _86;
    assign _98 = _87 ? _97 : _95;
    assign _100 = _98 == _102;
    assign _101 = ~ _100;
    assign _17 = _101;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _36;
        else
            m_valid_q <= _17;
    end
    assign _29 = m_valid_q & m_axis_tready;
    assign _18 = _29;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _36;
        else
            back1_credit <= _18;
    end
    assign _73 = ~ back1_credit;
    assign _38 = s_axis_tvalid & s_ready_q;
    assign _74 = _38 & _73;
    assign _85 = _74 ? _84 : _82;
    assign _103 = _85 == _102;
    assign _104 = ~ _103;
    assign _20 = _104;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _36;
        else
            s_ready_q <= _20;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c2_f2_b1_000 (
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

    wire [3:0] _26;
    wire [3:0] _33;
    wire [3:0] _34;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _43;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire [3:0] _7;
    reg [3:0] fwd2_data;
    wire _51;
    wire _55;
    wire _56;
    wire _54;
    wire _58;
    wire _59;
    wire _8;
    reg wp;
    reg [3:0] _73[0:1];
    wire _66;
    wire _64;
    wire _68;
    wire _69;
    wire _9;
    reg rp;
    wire [3:0] fifo_head;
    wire [1:0] _110;
    wire [1:0] _88;
    wire [1:0] _89;
    wire [1:0] _86;
    wire [1:0] _83;
    wire [1:0] _12;
    reg [1:0] credits;
    wire _80;
    wire _81;
    wire [1:0] _87;
    wire [1:0] _102;
    wire [1:0] _99;
    wire [1:0] _14;
    reg [1:0] cnt;
    wire _93;
    wire _94;
    wire [1:0] _100;
    wire _91;
    wire vdd;
    wire rst;
    wire _17;
    reg fwd1_valid;
    wire _18;
    reg fwd2_valid;
    wire _92;
    wire [1:0] _103;
    wire _108;
    wire _109;
    wire _19;
    reg m_valid_q;
    wire _31;
    wire _20;
    reg back1_credit;
    wire _78;
    wire _40;
    wire _79;
    wire [1:0] _90;
    wire _111;
    wire _112;
    wire _22;
    reg s_ready_q;
    assign _26 = 4'b0000;
    assign _33 = 4'b0001;
    assign _34 = f_out + _33;
    assign _1 = _34;
    always @(posedge aclk) begin
        if (rst)
            f_out <= _26;
        else
            if (_31)
                f_out <= _1;
    end
    assign _43 = f_in + _33;
    assign _3 = _43;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _26;
        else
            if (_40)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _7 = fwd1_data;
    always @(posedge aclk) begin
        fwd2_data <= _7;
    end
    assign _51 = 1'b0;
    assign _55 = 1'b1;
    assign _56 = wp + _55;
    assign _54 = wp == _55;
    assign _58 = _54 ? _51 : _56;
    assign _59 = fwd2_valid ? _58 : wp;
    assign _8 = _59;
    always @(posedge aclk) begin
        if (rst)
            wp <= _51;
        else
            wp <= _8;
    end
    always @(posedge aclk) begin
        if (fwd2_valid)
            _73[wp] <= fwd2_data;
    end
    assign _66 = rp + _55;
    assign _64 = rp == _55;
    assign _68 = _64 ? _51 : _66;
    assign _69 = _31 ? _68 : rp;
    assign _9 = _69;
    always @(posedge aclk) begin
        if (rst)
            rp <= _51;
        else
            rp <= _9;
    end
    assign fifo_head = _73[rp];
    assign _110 = 2'b00;
    assign _88 = 2'b01;
    assign _89 = credits - _88;
    assign _86 = credits + _88;
    assign _83 = 2'b10;
    assign _12 = _90;
    always @(posedge aclk) begin
        if (rst)
            credits <= _83;
        else
            credits <= _12;
    end
    assign _80 = ~ _40;
    assign _81 = _80 & back1_credit;
    assign _87 = _81 ? _86 : credits;
    assign _102 = cnt + _88;
    assign _99 = cnt - _88;
    assign _14 = _103;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _110;
        else
            cnt <= _14;
    end
    assign _93 = ~ fwd2_valid;
    assign _94 = _93 & _31;
    assign _100 = _94 ? _99 : cnt;
    assign _91 = ~ _31;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _17 = _40;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _51;
        else
            fwd1_valid <= _17;
    end
    assign _18 = fwd1_valid;
    always @(posedge aclk) begin
        if (rst)
            fwd2_valid <= _51;
        else
            fwd2_valid <= _18;
    end
    assign _92 = fwd2_valid & _91;
    assign _103 = _92 ? _102 : _100;
    assign _108 = _103 == _110;
    assign _109 = ~ _108;
    assign _19 = _109;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _51;
        else
            m_valid_q <= _19;
    end
    assign _31 = m_valid_q & m_axis_tready;
    assign _20 = _31;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _51;
        else
            back1_credit <= _20;
    end
    assign _78 = ~ back1_credit;
    assign _40 = s_axis_tvalid & s_ready_q;
    assign _79 = _40 & _78;
    assign _90 = _79 ? _89 : _87;
    assign _111 = _90 == _110;
    assign _112 = ~ _111;
    assign _22 = _112;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _51;
        else
            s_ready_q <= _22;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c3_f0_b2_000 (
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

    wire [3:0] _23;
    wire [3:0] _30;
    wire [3:0] _31;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _40;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [1:0] _42;
    wire [1:0] _46;
    wire [1:0] _47;
    wire [1:0] _44;
    wire _45;
    wire [1:0] _49;
    wire [1:0] _50;
    wire [1:0] _6;
    reg [1:0] wp;
    reg [3:0] _61[0:2];
    wire [1:0] _57;
    wire _55;
    wire [1:0] _59;
    wire [1:0] _60;
    wire [1:0] _7;
    reg [1:0] rp;
    wire [3:0] fifo_head;
    wire _35;
    wire [1:0] _77;
    wire [1:0] _74;
    wire [1:0] _71;
    wire [1:0] _10;
    reg [1:0] credits;
    wire _68;
    wire _69;
    wire [1:0] _75;
    wire [1:0] _90;
    wire [1:0] _87;
    wire vdd;
    wire rst;
    wire [1:0] _14;
    reg [1:0] cnt;
    wire _81;
    wire _82;
    wire [1:0] _88;
    wire _79;
    wire _80;
    wire [1:0] _91;
    wire _93;
    wire _94;
    wire _15;
    reg m_valid_q;
    wire _28;
    wire _16;
    reg back1_credit;
    wire _17;
    reg back2_credit;
    wire _66;
    wire _37;
    wire _67;
    wire [1:0] _78;
    wire _99;
    wire _100;
    wire _19;
    reg s_ready_q;
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
    assign _40 = f_in + _30;
    assign _3 = _40;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _23;
        else
            if (_37)
                f_in <= _3;
    end
    assign _42 = 2'b00;
    assign _46 = 2'b01;
    assign _47 = wp + _46;
    assign _44 = 2'b10;
    assign _45 = wp == _44;
    assign _49 = _45 ? _42 : _47;
    assign _50 = _37 ? _49 : wp;
    assign _6 = _50;
    always @(posedge aclk) begin
        if (rst)
            wp <= _42;
        else
            wp <= _6;
    end
    always @(posedge aclk) begin
        if (_37)
            _61[wp] <= s_axis_tdata;
    end
    assign _57 = rp + _46;
    assign _55 = rp == _44;
    assign _59 = _55 ? _42 : _57;
    assign _60 = _28 ? _59 : rp;
    assign _7 = _60;
    always @(posedge aclk) begin
        if (rst)
            rp <= _42;
        else
            rp <= _7;
    end
    assign fifo_head = _61[rp];
    assign _35 = 1'b0;
    assign _77 = credits - _46;
    assign _74 = credits + _46;
    assign _71 = 2'b11;
    assign _10 = _78;
    always @(posedge aclk) begin
        if (rst)
            credits <= _71;
        else
            credits <= _10;
    end
    assign _68 = ~ _37;
    assign _69 = _68 & back2_credit;
    assign _75 = _69 ? _74 : credits;
    assign _90 = cnt + _46;
    assign _87 = cnt - _46;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _14 = _91;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _42;
        else
            cnt <= _14;
    end
    assign _81 = ~ _37;
    assign _82 = _81 & _28;
    assign _88 = _82 ? _87 : cnt;
    assign _79 = ~ _28;
    assign _80 = _37 & _79;
    assign _91 = _80 ? _90 : _88;
    assign _93 = _91 == _42;
    assign _94 = ~ _93;
    assign _15 = _94;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _35;
        else
            m_valid_q <= _15;
    end
    assign _28 = m_valid_q & m_axis_tready;
    assign _16 = _28;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _35;
        else
            back1_credit <= _16;
    end
    assign _17 = back1_credit;
    always @(posedge aclk) begin
        if (rst)
            back2_credit <= _35;
        else
            back2_credit <= _17;
    end
    assign _66 = ~ back2_credit;
    assign _37 = s_axis_tvalid & s_ready_q;
    assign _67 = _37 & _66;
    assign _78 = _67 ? _77 : _75;
    assign _99 = _78 == _42;
    assign _100 = ~ _99;
    assign _19 = _100;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _35;
        else
            s_ready_q <= _19;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c5_f2_b2_000 (
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

    wire [3:0] _27;
    wire [3:0] _34;
    wire [3:0] _35;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _44;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire [3:0] _7;
    reg [3:0] fwd2_data;
    wire [2:0] _52;
    wire [2:0] _56;
    wire [2:0] _57;
    wire [2:0] _54;
    wire _55;
    wire [2:0] _59;
    wire [2:0] _60;
    wire [2:0] _8;
    reg [2:0] wp;
    reg [3:0] _74[0:4];
    wire [2:0] _67;
    wire _65;
    wire [2:0] _69;
    wire [2:0] _70;
    wire [2:0] _9;
    reg [2:0] rp;
    wire [3:0] fifo_head;
    wire _39;
    wire [2:0] _90;
    wire [2:0] _87;
    wire [2:0] _84;
    wire [2:0] _12;
    reg [2:0] credits;
    wire _81;
    wire _82;
    wire [2:0] _88;
    wire [2:0] _103;
    wire [2:0] _100;
    wire [2:0] _14;
    reg [2:0] cnt;
    wire _94;
    wire _95;
    wire [2:0] _101;
    wire _92;
    wire vdd;
    wire rst;
    wire _17;
    reg fwd1_valid;
    wire _18;
    reg fwd2_valid;
    wire _93;
    wire [2:0] _104;
    wire _109;
    wire _110;
    wire _19;
    reg m_valid_q;
    wire _32;
    wire _20;
    reg back1_credit;
    wire _21;
    reg back2_credit;
    wire _79;
    wire _41;
    wire _80;
    wire [2:0] _91;
    wire _115;
    wire _116;
    wire _23;
    reg s_ready_q;
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
    assign _44 = f_in + _34;
    assign _3 = _44;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _27;
        else
            if (_41)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _7 = fwd1_data;
    always @(posedge aclk) begin
        fwd2_data <= _7;
    end
    assign _52 = 3'b000;
    assign _56 = 3'b001;
    assign _57 = wp + _56;
    assign _54 = 3'b100;
    assign _55 = wp == _54;
    assign _59 = _55 ? _52 : _57;
    assign _60 = fwd2_valid ? _59 : wp;
    assign _8 = _60;
    always @(posedge aclk) begin
        if (rst)
            wp <= _52;
        else
            wp <= _8;
    end
    always @(posedge aclk) begin
        if (fwd2_valid)
            _74[wp] <= fwd2_data;
    end
    assign _67 = rp + _56;
    assign _65 = rp == _54;
    assign _69 = _65 ? _52 : _67;
    assign _70 = _32 ? _69 : rp;
    assign _9 = _70;
    always @(posedge aclk) begin
        if (rst)
            rp <= _52;
        else
            rp <= _9;
    end
    assign fifo_head = _74[rp];
    assign _39 = 1'b0;
    assign _90 = credits - _56;
    assign _87 = credits + _56;
    assign _84 = 3'b101;
    assign _12 = _91;
    always @(posedge aclk) begin
        if (rst)
            credits <= _84;
        else
            credits <= _12;
    end
    assign _81 = ~ _41;
    assign _82 = _81 & back2_credit;
    assign _88 = _82 ? _87 : credits;
    assign _103 = cnt + _56;
    assign _100 = cnt - _56;
    assign _14 = _104;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _52;
        else
            cnt <= _14;
    end
    assign _94 = ~ fwd2_valid;
    assign _95 = _94 & _32;
    assign _101 = _95 ? _100 : cnt;
    assign _92 = ~ _32;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _17 = _41;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _39;
        else
            fwd1_valid <= _17;
    end
    assign _18 = fwd1_valid;
    always @(posedge aclk) begin
        if (rst)
            fwd2_valid <= _39;
        else
            fwd2_valid <= _18;
    end
    assign _93 = fwd2_valid & _92;
    assign _104 = _93 ? _103 : _101;
    assign _109 = _104 == _52;
    assign _110 = ~ _109;
    assign _19 = _110;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _39;
        else
            m_valid_q <= _19;
    end
    assign _32 = m_valid_q & m_axis_tready;
    assign _20 = _32;
    always @(posedge aclk) begin
        if (rst)
            back1_credit <= _39;
        else
            back1_credit <= _20;
    end
    assign _21 = back1_credit;
    always @(posedge aclk) begin
        if (rst)
            back2_credit <= _39;
        else
            back2_credit <= _21;
    end
    assign _79 = ~ back2_credit;
    assign _41 = s_axis_tvalid & s_ready_q;
    assign _80 = _41 & _79;
    assign _91 = _80 ? _90 : _88;
    assign _115 = _91 == _52;
    assign _116 = ~ _115;
    assign _23 = _116;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _39;
        else
            s_ready_q <= _23;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

module credit_chan_hc_w4_c4_f3_b0_000 (
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

    wire [3:0] _27;
    wire [3:0] _34;
    wire [3:0] _35;
    wire [3:0] _1;
    reg [3:0] f_out;
    wire [3:0] _44;
    wire [3:0] _3;
    reg [3:0] f_in;
    wire [3:0] _6;
    reg [3:0] fwd1_data;
    wire [3:0] _7;
    reg [3:0] fwd2_data;
    wire [3:0] _8;
    reg [3:0] fwd3_data;
    wire [1:0] _55;
    wire [1:0] _59;
    wire [1:0] _60;
    wire [1:0] _57;
    wire _58;
    wire [1:0] _62;
    wire [1:0] _63;
    wire [1:0] _9;
    reg [1:0] wp;
    reg [3:0] _77[0:3];
    wire [1:0] _70;
    wire _68;
    wire [1:0] _72;
    wire [1:0] _73;
    wire [1:0] _10;
    reg [1:0] rp;
    wire [3:0] fifo_head;
    wire _39;
    wire [2:0] _114;
    wire [2:0] _89;
    wire [2:0] _90;
    wire [2:0] _87;
    wire [2:0] _84;
    wire [2:0] _13;
    reg [2:0] credits;
    wire _81;
    wire _82;
    wire [2:0] _88;
    wire [2:0] _103;
    wire [2:0] _100;
    wire [2:0] _15;
    reg [2:0] cnt;
    wire _94;
    wire _95;
    wire [2:0] _101;
    wire _92;
    wire vdd;
    wire rst;
    wire _18;
    reg fwd1_valid;
    wire _19;
    reg fwd2_valid;
    wire _20;
    reg fwd3_valid;
    wire _93;
    wire [2:0] _104;
    wire _112;
    wire _113;
    wire _21;
    reg m_valid_q;
    wire _32;
    wire _79;
    wire _41;
    wire _80;
    wire [2:0] _91;
    wire _115;
    wire _116;
    wire _23;
    reg s_ready_q;
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
    assign _44 = f_in + _34;
    assign _3 = _44;
    always @(posedge aclk) begin
        if (rst)
            f_in <= _27;
        else
            if (_41)
                f_in <= _3;
    end
    assign _6 = s_axis_tdata;
    always @(posedge aclk) begin
        fwd1_data <= _6;
    end
    assign _7 = fwd1_data;
    always @(posedge aclk) begin
        fwd2_data <= _7;
    end
    assign _8 = fwd2_data;
    always @(posedge aclk) begin
        fwd3_data <= _8;
    end
    assign _55 = 2'b00;
    assign _59 = 2'b01;
    assign _60 = wp + _59;
    assign _57 = 2'b11;
    assign _58 = wp == _57;
    assign _62 = _58 ? _55 : _60;
    assign _63 = fwd3_valid ? _62 : wp;
    assign _9 = _63;
    always @(posedge aclk) begin
        if (rst)
            wp <= _55;
        else
            wp <= _9;
    end
    always @(posedge aclk) begin
        if (fwd3_valid)
            _77[wp] <= fwd3_data;
    end
    assign _70 = rp + _59;
    assign _68 = rp == _57;
    assign _72 = _68 ? _55 : _70;
    assign _73 = _32 ? _72 : rp;
    assign _10 = _73;
    always @(posedge aclk) begin
        if (rst)
            rp <= _55;
        else
            rp <= _10;
    end
    assign fifo_head = _77[rp];
    assign _39 = 1'b0;
    assign _114 = 3'b000;
    assign _89 = 3'b001;
    assign _90 = credits - _89;
    assign _87 = credits + _89;
    assign _84 = 3'b100;
    assign _13 = _91;
    always @(posedge aclk) begin
        if (rst)
            credits <= _84;
        else
            credits <= _13;
    end
    assign _81 = ~ _41;
    assign _82 = _81 & _32;
    assign _88 = _82 ? _87 : credits;
    assign _103 = cnt + _89;
    assign _100 = cnt - _89;
    assign _15 = _104;
    always @(posedge aclk) begin
        if (rst)
            cnt <= _114;
        else
            cnt <= _15;
    end
    assign _94 = ~ fwd3_valid;
    assign _95 = _94 & _32;
    assign _101 = _95 ? _100 : cnt;
    assign _92 = ~ _32;
    assign vdd = 1'b1;
    assign rst = ~ aresetn;
    assign _18 = _41;
    always @(posedge aclk) begin
        if (rst)
            fwd1_valid <= _39;
        else
            fwd1_valid <= _18;
    end
    assign _19 = fwd1_valid;
    always @(posedge aclk) begin
        if (rst)
            fwd2_valid <= _39;
        else
            fwd2_valid <= _19;
    end
    assign _20 = fwd2_valid;
    always @(posedge aclk) begin
        if (rst)
            fwd3_valid <= _39;
        else
            fwd3_valid <= _20;
    end
    assign _93 = fwd3_valid & _92;
    assign _104 = _93 ? _103 : _101;
    assign _112 = _104 == _114;
    assign _113 = ~ _112;
    assign _21 = _113;
    always @(posedge aclk) begin
        if (rst)
            m_valid_q <= _39;
        else
            m_valid_q <= _21;
    end
    assign _32 = m_valid_q & m_axis_tready;
    assign _79 = ~ _32;
    assign _41 = s_axis_tvalid & s_ready_q;
    assign _80 = _41 & _79;
    assign _91 = _80 ? _90 : _88;
    assign _115 = _91 == _114;
    assign _116 = ~ _115;
    assign _23 = _116;
    always @(posedge aclk) begin
        if (rst)
            s_ready_q <= _39;
        else
            s_ready_q <= _23;
    end
    assign s_axis_tready = s_ready_q;
    assign m_axis_tvalid = m_valid_q;
    assign m_axis_tdata = fifo_head;
    assign f_in_o = f_in;
    assign f_out_o = f_out;

endmodule

// credit_chan: wrapper generated by gen.exe (brief 171). Same parameters and ports as ip_lib/credit_chan/rtl/credit_chan.sv;
// the datapath is the Hardcaml module of the matching parameter point.
module credit_chan #(
    parameter int W        = 32,
    parameter int CREDITS  = 8,
    parameter int LF       = 1,
    parameter int LB       = 1,
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
        if (W == 4 && CREDITS == 1 && LF == 0 && LB == 0 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c1_f0_b0_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 2 && LF == 0 && LB == 0 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c2_f0_b0_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 1 && LF == 1 && LB == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c1_f1_b1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 2 && LF == 1 && LB == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c2_f1_b1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 3 && LF == 1 && LB == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c3_f1_b1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 4 && LF == 1 && LB == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c4_f1_b1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 2 && LF == 2 && LB == 1 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c2_f2_b1_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 3 && LF == 0 && LB == 2 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c3_f0_b2_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 5 && LF == 2 && LB == 2 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c5_f2_b2_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end else if (W == 4 && CREDITS == 4 && LF == 3 && LB == 0 && TLAST_EN == 0 && TKEEP_EN == 0 && TUSER_W == 0) begin : g_hc
            credit_chan_hc_w4_c4_f3_b0_000 u (.aclk, .aresetn, .s_axis_tvalid, .s_axis_tready, .s_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tdata,
                .f_in_o, .f_out_o);
            assign m_axis_tlast = 1'b0;
            assign m_axis_tkeep = '0;
            assign m_axis_tuser = '0;
        end
    endgenerate
endmodule
