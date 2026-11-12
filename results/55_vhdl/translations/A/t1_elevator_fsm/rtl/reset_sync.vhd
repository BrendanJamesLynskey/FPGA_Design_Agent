library ieee;
use ieee.std_logic_1164.all;

entity reset_sync is
  port (
    clk         : in  std_logic;
    rst_n_async : in  std_logic;
    rst         : out std_logic
  );
end entity reset_sync;

architecture rtl of reset_sync is
  signal sync_pipe : std_logic_vector(1 downto 0);
begin
  process (clk, rst_n_async)
  begin
    if rst_n_async = '0' then
      sync_pipe <= (others => '1');
    elsif rising_edge(clk) then
      sync_pipe <= sync_pipe(0) & '0';
    end if;
  end process;

  rst <= sync_pipe(1);
end architecture rtl;
