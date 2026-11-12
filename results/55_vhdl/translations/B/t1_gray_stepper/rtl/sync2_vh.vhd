library ieee;
use ieee.std_logic_1164.all;

entity sync2_vh is
    port (
        clk : in  std_logic;
        rst : in  std_logic;
        d   : in  std_logic;
        q   : out std_logic
    );
end entity sync2_vh;

architecture rtl of sync2_vh is
    signal meta_reg : std_logic := '0';
    signal sync_reg : std_logic := '0';
begin
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                meta_reg <= '0';
                sync_reg <= '0';
            else
                meta_reg <= d;
                sync_reg <= meta_reg;
            end if;
        end if;
    end process;

    q <= sync_reg;
end architecture rtl;
