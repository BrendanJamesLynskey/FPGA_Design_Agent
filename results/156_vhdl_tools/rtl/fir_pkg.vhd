-- fir_pkg: types and helper functions of the 16-tap FIR used by brief 156's simulator comparison.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package fir_pkg is
    constant TAPS : positive := 16;
    constant DW   : positive := 16;                 -- sample width, signed
    constant CW   : positive := 12;                 -- coefficient width, signed
    constant AW   : positive := 36;                 -- accumulator width: DW + CW + clog2(TAPS) fits in 32, kept wider

    type sample_vec_t is array (0 to TAPS - 1) of signed(DW - 1 downto 0);
    type coef_vec_t   is array (0 to TAPS - 1) of signed(CW - 1 downto 0);
    type prod_vec_t   is array (0 to TAPS - 1) of signed(DW + CW - 1 downto 0);

    type stage_t is record
        valid : std_logic;
        sum   : signed(AW - 1 downto 0);
    end record;
    type stage_vec_t is array (natural range <>) of stage_t;

    -- the default coefficients: a symmetric low-pass shape, written out so every simulator reads the same table
    function default_coefs return coef_vec_t;
    -- saturate a wide accumulator to the output width
    function sat16(x : signed) return signed;
end package fir_pkg;

package body fir_pkg is
    function default_coefs return coef_vec_t is
        variable c : coef_vec_t;
        constant half : integer_vector(0 to 7) := (-12, 7, 31, 78, 152, 241, 329, 391);
    begin
        for i in 0 to 7 loop
            c(i)           := to_signed(half(i), CW);
            c(TAPS - 1 - i) := to_signed(half(i), CW);
        end loop;
        return c;
    end function;

    function sat16(x : signed) return signed is
        constant MAXV : signed(x'length - 1 downto 0) := to_signed(2 ** (DW - 1) - 1, x'length);
        constant MINV : signed(x'length - 1 downto 0) := to_signed(-(2 ** (DW - 1)), x'length);
    begin
        if x > MAXV then
            return to_signed(2 ** (DW - 1) - 1, DW);
        elsif x < MINV then
            return to_signed(-(2 ** (DW - 1)), DW);
        else
            return resize(x, DW);
        end if;
    end function;
end package body fir_pkg;
