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
    signal sync_ff1 : std_logic;
    signal sync_ff2 : std_logic;
begin
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                sync_ff1 <= '0';
                sync_ff2 <= '0';
            else
                sync_ff1 <= d;
                sync_ff2 <= sync_ff1;
            end if;
        end if;
    end process;

    q <= sync_ff2;
end architecture rtl;
