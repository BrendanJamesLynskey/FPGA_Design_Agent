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
    signal meta : std_logic;
    signal sync : std_logic;
begin
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                meta <= '0';
                sync <= '0';
            else
                meta <= d;
                sync <= meta;
            end if;
        end if;
    end process;

    q <= sync;
end architecture rtl;
