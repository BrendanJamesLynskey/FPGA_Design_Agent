library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity psl_cnt is port (clk, rst, en : in std_logic; q : out std_logic_vector(3 downto 0)); end;
architecture rtl of psl_cnt is signal c : unsigned(3 downto 0) := (others => '0'); begin
  process (clk) begin
    if rising_edge(clk) then
      if rst = '1' then c <= (others => '0'); elsif en = '1' then
        if c = 9 then c <= (others => '0'); else c <= c + 1; end if;    -- decade counter
      end if;
    end if;
  end process;
  q <= std_logic_vector(c);
  -- psl default clock is rising_edge(clk);
  -- psl a_range : assert always (c <= 9);
  -- psl a_reset : assert always (rst = '1') -> next (c = 0);
  -- psl c_wrap  : cover {c = 9; c = 0};
end;
