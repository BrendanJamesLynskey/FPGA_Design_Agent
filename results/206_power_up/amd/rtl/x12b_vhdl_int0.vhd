-- Brief 206 arm X12b (amendment): the X12 counter with an explicit initial value of 0, the pair for X12.
-- VHDL's default initial value of an integer range is its left bound (-8 here); this probe shows what the synthesis tool
-- loads at power-up for it. INITV is unused; kept so every arm has the same generic.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity x12b_vhdl_int0 is
  generic (INITV : integer := 1);
  port (clk : in std_logic; inc : in std_logic; q : out std_logic_vector(3 downto 0));
end entity;

architecture rtl of x12b_vhdl_int0 is
  signal cnt : integer range -8 to 7 := 0;   -- explicit 0: the pair for x12_vhdl_int
begin
  process (clk) begin
    if rising_edge(clk) then
      if inc = '1' then
        if cnt = 7 then cnt <= -8; else cnt <= cnt + 1; end if;
      end if;
    end if;
  end process;
  q <= std_logic_vector(to_signed(cnt, 4));
end architecture;
