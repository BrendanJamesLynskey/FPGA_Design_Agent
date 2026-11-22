// divider_hr_lemma_fv: the step lemmas of the radix-4 SRT recurrence (brief 139c), checked by SymbiYosys with the slang front end.
//   The digit-recurrence argument is an induction on the number of digit steps: if the partial remainder u satisfies 3|u| <= 2b (the convergence
//   bound) and the quotient so far is Q with a * 4**(j-1) = b * Q + u, then the next step keeps both. The induction is the same for every K, so the
//   facts the RTL must supply are combinational statements about one step, and they are checked here for ALL inputs at a fixed width W:
//     L1  the first step: from the dividend a (normalised) and divisor b (normalised) the first digit is 0, 1 or 2 and 3|a - q*b| <= 2b;
//     L2  the carry-save step: for ANY two words (us, uc) whose sum u satisfies the bound, the new words sum to 4u - q*b (mod 2**(W+3)) and satisfy the bound;
//     L3  the carry-propagate step: the same for the W + 1 bit remainder;
//     L4  the on-the-fly conversion: if QM = Q - 1 then Q' = 4Q + q and QM' = Q' - 1 (mod 2**QW) for every digit -2..2;
//     L5  the fix: with the bound, the remainder returned is u (u >= 0) or u + b (u < 0) and lies in [0, b), and the quotient is QM when u < 0.
//   They are combinational: a depth-1 check is complete. The lemma that the estimate (the top bits of the two words) is within one unit of the top
//   bits of the sum is inside L2 (it holds for every split of u into two words, not only the ones the compressor produces).
module divider_hr_lemma_fv #(
    parameter int W  = 8,
    parameter int QW = 9
) (
    input logic          clk,
    input logic [W-1:0]  a,
    input logic [W-1:0]  b,
    input logic [W+2:0]  us,
    input logic [W+2:0]  uc,
    input logic [W:0]    ur,
    input logic [QW-1:0] qq,
    input logic [2:0]    qd
);
    localparam int WW = W + 3;
    localparam int XW = W + 8;                           // signed arithmetic width for the products and sums

    always_comb a_norm: assume (a[W-1] && b[W-1]);

    function automatic logic signed [XW-1:0] sext(input logic [WW-1:0] v);
        return {{(XW-WW){v[WW-1]}}, v};
    endfunction
    function automatic logic signed [XW-1:0] abs3(input logic signed [XW-1:0] v);
        return (v < 0) ? -(3 * v) : 3 * v;
    endfunction

    logic signed [XW-1:0] bs;
    always_comb bs = $signed({{(XW-W){1'b0}}, b});

    // L1: first step
    logic [WW-1:0] us1, uc1;
    logic [2:0]    q1;
    divider_hr_cs_step #(.W(W)) u_l1 (.first(1'b1), .us({3'b000, a}), .uc('0), .b(b), .us_n(us1), .uc_n(uc1), .q(q1));
    logic signed [XW-1:0] u1, as, q1s;
    always_comb begin
        u1  = sext(us1 + uc1);
        as  = $signed({{(XW-W){1'b0}}, a});
        q1s = {{(XW-3){q1[2]}}, q1};
        l1_digit: assert (q1 == 3'b000 || q1 == 3'b001 || q1 == 3'b010);
        l1_value: assert (u1 == as - q1s * bs);
        l1_bound: assert (abs3(u1) <= 2 * bs);
    end

    // L2: carry-save step
    logic signed [XW-1:0] u, u2, q2s;
    logic [WW-1:0] us2, uc2;
    logic [2:0]    q2;
    divider_hr_cs_step #(.W(W)) u_l2 (.first(1'b0), .us(us), .uc(uc), .b(b), .us_n(us2), .uc_n(uc2), .q(q2));
    always_comb begin
        u   = sext(us + uc);
        u2  = sext(us2 + uc2);
        q2s = {{(XW-3){q2[2]}}, q2};
        l2_assume: assume (abs3(u) <= 2 * bs);
        l2_digit:  assert (q2 != 3'b011 && q2 != 3'b100);
        l2_value:  assert (u2 == 4 * u - q2s * bs);
        l2_bound:  assert (abs3(u2) <= 2 * bs);
    end

    // L3: carry-propagate step (the first-step check of this form is the same as L1 with the same selection)
    logic [W:0]   ur_n;
    logic [2:0]   q3;
    divider_hr_cpa_step #(.W(W)) u_l3 (.first(1'b0), .u(ur), .b(b), .u_n(ur_n), .q(q3));
    logic signed [XW-1:0] u3, u3n, q3s;
    always_comb begin
        u3  = {{(XW-W-1){ur[W]}}, ur};
        u3n = {{(XW-W-1){ur_n[W]}}, ur_n};
        q3s = {{(XW-3){q3[2]}}, q3};
        l3_assume: assume (abs3(u3) <= 2 * bs);
        l3_value:  assert (u3n == 4 * u3 - q3s * bs);
        l3_bound:  assert (abs3(u3n) <= 2 * bs);
    end
    logic [W:0]   ur1;
    logic [2:0]   q3a;
    divider_hr_cpa_step #(.W(W)) u_l3a (.first(1'b1), .u({1'b0, a}), .b(b), .u_n(ur1), .q(q3a));
    logic signed [XW-1:0] u3a;
    always_comb begin
        u3a = {{(XW-W-1){ur1[W]}}, ur1};
        l3a_value: assert (u3a == as - $signed({{(XW-3){q3a[2]}}, q3a}) * bs && abs3(u3a) <= 2 * bs);
    end

    // L4: on-the-fly conversion
    logic [QW-1:0] qm, qo, qmo;
    always_comb begin
        qm = qq - 1'b1;
        l4_digit_assume: assume (qd == 3'b000 || qd == 3'b001 || qd == 3'b010 || qd == 3'b111 || qd == 3'b110);
    end
    divider_hr_otf #(.QW(QW)) u_l4 (.q(qd), .qi(qq), .qmi(qm), .qo(qo), .qmo(qmo));
    logic [QW-1:0] qexp;
    always_comb begin
        qexp = {qq[QW-3:0], 2'b00} + {{(QW-3){qd[2]}}, qd};
        l4_q:  assert (qo == qexp);
        l4_qm: assert (qmo == qexp - 1'b1);
    end

    // L5: the fix, carry-save and carry-propagate
    logic [QW-1:0] quo_c, quo_p;
    logic [W-1:0]  rem_c, rem_p;
    divider_hr_fix #(.W(W), .QW(QW), .CS(1'b1)) u_l5c (.us(us), .uc(uc), .b(b), .qq(qq), .qm(qm), .quo(quo_c), .rem(rem_c));
    divider_hr_fix #(.W(W), .QW(QW), .CS(1'b0)) u_l5p (.us({2'b00, ur}), .uc('0), .b(b), .qq(qq), .qm(qm), .quo(quo_p), .rem(rem_p));
    logic signed [XW-1:0] rc, rp, expc, expp;
    always_comb begin
        rc   = $signed({{(XW-W){1'b0}}, rem_c});
        rp   = $signed({{(XW-W){1'b0}}, rem_p});
        expc = (u < 0) ? u + bs : u;
        expp = (u3 < 0) ? u3 + bs : u3;
        l5c_rem: assert (rc == expc && rc >= 0 && rc < bs && quo_c == ((u < 0) ? qm : qq));
        l5p_rem: assert (rp == expp && rp >= 0 && rp < bs && quo_p == ((u3 < 0) ? qm : qq));
    end
endmodule
