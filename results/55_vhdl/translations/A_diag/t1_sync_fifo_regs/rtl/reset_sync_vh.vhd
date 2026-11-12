library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity reset_sync_vh is
    port (
        clk          : in  std_logic;
        rst_n_async  : in  std_logic;
        rst          : out std_logic
    );
end entity reset_sync_vh;

architecture rtl of reset_sync_vh is
    signal reset_meta : std_logic;
    signal reset_sync_ff : std_logic;
begin
    process (clk, rst_n_async)
    begin
        if rst_n_async = '0' then
            reset_meta    <= '0';
            reset_sync_ff <= '0';
        elsif rising_edge(clk) then
            reset_meta    <= '1';
            reset_sync_ff <= reset_meta;
        end if;
    end process;

    rst <= not reset_sync_ff;
end architecture rtl;
