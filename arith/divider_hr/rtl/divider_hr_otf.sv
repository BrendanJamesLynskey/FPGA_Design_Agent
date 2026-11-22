// divider_hr_otf: on-the-fly conversion of one signed radix-4 digit (brief 139c). Keeps the quotient so far Q and QM = Q - 1 in plain binary so no
// carry-propagate adder is ever needed: Q' = 4Q + q and QM' = Q' - 1 are formed by choosing between Q and QM and appending two bits (mod 2**QW).
module divider_hr_otf #(
    parameter int QW = 9
) (
    input  logic [2:0]    q,         // 3-bit two's complement digit, -2..2
    input  logic [QW-1:0] qi,
    input  logic [QW-1:0] qmi,
    output logic [QW-1:0] qo,
    output logic [QW-1:0] qmo
);
    logic unused;
    assign unused = &{1'b0, qi[QW-1:QW-2], qmi[QW-1:QW-2]};     // shifted out
    always_comb begin
        case (q)
            3'b010:  begin qo = {qi[QW-3:0], 2'b10};  qmo = {qi[QW-3:0], 2'b01};  end   // +2
            3'b001:  begin qo = {qi[QW-3:0], 2'b01};  qmo = {qi[QW-3:0], 2'b00};  end   // +1
            3'b111:  begin qo = {qmi[QW-3:0], 2'b11}; qmo = {qmi[QW-3:0], 2'b10}; end   // -1
            3'b110:  begin qo = {qmi[QW-3:0], 2'b10}; qmo = {qmi[QW-3:0], 2'b01}; end   // -2
            default: begin qo = {qi[QW-3:0], 2'b00};  qmo = {qmi[QW-3:0], 2'b11}; end   //  0
        endcase
    end
endmodule
