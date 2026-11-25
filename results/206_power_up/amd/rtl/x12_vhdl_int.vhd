-- Brief 206 arm X12 (and Altera Q9): a VHDL integer register with no initial value.
-- VHDL's default initial value of an integer range is its left bound (-8 here); this probe shows what the synthesis tool
-- loads at power-up for it. INITV is unused; kept so every arm has the same generic.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity x12_vhdl_int is
  generic (INITV : integer := 1);
  port (clk : in std_logic; inc : in std_logic; q : out std_logic_vector(3 downto 0));
end entity;

architecture rtl of x12_vhdl_int is
  signal cnt : integer range -8 to 7;   -- no initialiser: the language default is -8
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
