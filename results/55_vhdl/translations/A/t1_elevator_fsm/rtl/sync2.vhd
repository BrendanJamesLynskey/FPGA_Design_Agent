library ieee;
use ieee.std_logic_1164.all;

entity sync2 is
  generic (
    WIDTH : integer := 1
  );
  port (
    clk : in  std_logic;
    rst : in  std_logic;
    d   : in  std_logic_vector(WIDTH - 1 downto 0);
    q   : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity sync2;

architecture rtl of sync2 is
  signal sync_stage : std_logic_vector(WIDTH - 1 downto 0);
  signal q_stage    : std_logic_vector(WIDTH - 1 downto 0);
begin
  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        sync_stage <= (others => '0');
        q_stage    <= (others => '0');
      else
        sync_stage <= d;
        q_stage    <= sync_stage;
      end if;
    end if;
  end process;

  q <= q_stage;
end architecture rtl;
