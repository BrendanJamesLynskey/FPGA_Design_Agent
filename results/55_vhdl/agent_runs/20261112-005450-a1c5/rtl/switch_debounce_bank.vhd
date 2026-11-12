library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity switch_debounce_bank is
  generic (
    DEBOUNCE_CYCLES : integer := 1000000
  );
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    switches  : in  std_logic_vector(15 downto 0);
    clean     : out std_logic_vector(15 downto 0);
    win_addr  : in  std_logic_vector(6 downto 0);
    win_wr    : in  std_logic;
    win_rd    : in  std_logic;
    win_wdata : in  std_logic_vector(31 downto 0);
    win_rdata : out std_logic_vector(31 downto 0)
  );
end entity switch_debounce_bank;

architecture rtl of switch_debounce_bank is
  function positive_value(n : integer) return positive is
  begin
    if n < 1 then
      return 1;
    end if;
    return n;
  end function;

  function counter_width(n : positive) return positive is
    variable v : natural := n - 1;
    variable w : positive := 1;
  begin
    while v > 1 loop
      v := v / 2;
      w := w + 1;
    end loop;
    return w;
  end function;

  constant QUALIFY_CYCLES : positive := positive_value(DEBOUNCE_CYCLES);
  constant COUNT_WIDTH : positive := counter_width(QUALIFY_CYCLES);
  type count_array_t is array (15 downto 0) of unsigned(COUNT_WIDTH - 1 downto 0);
  type byte_array_t is array (15 downto 0) of unsigned(7 downto 0);

  signal sync_meta  : std_logic_vector(15 downto 0) := (others => '0');
  signal sync_level : std_logic_vector(15 downto 0) := (others => '0');
  signal clean_reg  : std_logic_vector(15 downto 0) := (others => '0');
  signal qualify_count : count_array_t := (others => (others => '0'));
  signal change_count  : byte_array_t := (others => (others => '0'));
  signal edge_flags    : std_logic_vector(15 downto 0) := (others => '0');
  signal rising_enable : std_logic_vector(15 downto 0) := (others => '0');
  signal falling_enable : std_logic_vector(15 downto 0) := (others => '0');
  signal read_data : std_logic_vector(31 downto 0) := (others => '0');
begin
  clean <= clean_reg;
  win_rdata <= read_data;

  process (clk)
    variable flags_next : std_logic_vector(15 downto 0);
    variable addr_value : unsigned(6 downto 0);
    variable reg_value : std_logic_vector(31 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        sync_meta <= (others => '0');
        sync_level <= (others => '0');
        clean_reg <= (others => '0');
        qualify_count <= (others => (others => '0'));
        change_count <= (others => (others => '0'));
        edge_flags <= (others => '0');
        rising_enable <= (others => '0');
        falling_enable <= (others => '0');
        read_data <= (others => '0');
      else
        sync_meta <= switches;
        sync_level <= sync_meta;

        flags_next := edge_flags;
        if win_wr = '1' and unsigned(win_addr) = to_unsigned(4, 7) then
          flags_next := flags_next and not win_wdata(15 downto 0);
        end if;

        if win_wr = '1' and unsigned(win_addr) = to_unsigned(8, 7) then
          rising_enable <= win_wdata(15 downto 0);
        end if;
        if win_wr = '1' and unsigned(win_addr) = to_unsigned(12, 7) then
          falling_enable <= win_wdata(15 downto 0);
        end if;

        for i in 0 to 15 loop
          if sync_level(i) = clean_reg(i) then
            qualify_count(i) <= (others => '0');
          elsif qualify_count(i) = to_unsigned(QUALIFY_CYCLES - 1, COUNT_WIDTH) then
            qualify_count(i) <= (others => '0');
            clean_reg(i) <= sync_level(i);
            change_count(i) <= change_count(i) + 1;
            if sync_level(i) = '1' then
              if rising_enable(i) = '1' then
                flags_next(i) := '1';
              end if;
            elsif falling_enable(i) = '1' then
              flags_next(i) := '1';
            end if;
          else
            qualify_count(i) <= qualify_count(i) + 1;
          end if;
        end loop;
        edge_flags <= flags_next;

        if win_rd = '1' then
          addr_value := unsigned(win_addr);
          reg_value := (others => '0');
          case to_integer(addr_value) is
            when 0 => reg_value(15 downto 0) := clean_reg;
            when 4 => reg_value(15 downto 0) := edge_flags;
            when 8 => reg_value(15 downto 0) := rising_enable;
            when 12 => reg_value(15 downto 0) := falling_enable;
            when 16 | 20 | 24 | 28 | 32 | 36 | 40 | 44 |
                 48 | 52 | 56 | 60 | 64 | 68 | 72 | 76 =>
              reg_value(7 downto 0) := std_logic_vector(change_count((to_integer(addr_value) - 16) / 4));
            when others => null;
          end case;
          read_data <= reg_value;
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
