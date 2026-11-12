library ieee;
use ieee.std_logic_1164.all;

entity reset_sync is
    port (
        clk          : in  std_logic;
        rst_n_async  : in  std_logic;
        rst          : out std_logic
    );
end entity reset_sync;

architecture rtl of reset_sync is
    signal reset_pipe : std_logic_vector(1 downto 0);
begin
    process (clk, rst_n_async)
    begin
        if rst_n_async = '0' then
            reset_pipe <= (others => '0');
        elsif rising_edge(clk) then
            reset_pipe <= reset_pipe(0) & '1';
        end if;
    end process;

    rst <= not reset_pipe(1);
end architecture rtl;
