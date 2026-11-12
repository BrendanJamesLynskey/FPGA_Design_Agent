library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1_sync_fifo_regs_top is
  generic (
    CLKS_PER_BIT   : integer := 868;
    TIMEOUT_CYCLES : integer := 100000000;
    BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000"
  );
  port (
    CLK100MHZ   : in  std_logic;
    CPU_RESETN  : in  std_logic;
    UART_TXD_IN : in  std_logic;
    UART_RXD_OUT: out std_logic;
    LED         : out std_logic_vector(15 downto 0)
  );
end entity t1_sync_fifo_regs_top;

architecture rtl of t1_sync_fifo_regs_top is
  component fpga_shell is
    generic (
      CLKS_PER_BIT   : integer := 868;
      TIMEOUT_CYCLES : integer := 100000;
      DESIGN_ID      : std_logic_vector(31 downto 0) := x"00000000";
      BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000"
    );
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;
      uart_rx   : in  std_logic;
      uart_tx   : out std_logic;
      win_addr  : out std_logic_vector(6 downto 0);
      win_wr    : out std_logic;
      win_rd    : out std_logic;
      win_wdata : out std_logic_vector(31 downto 0);
      win_rdata : in  std_logic_vector(31 downto 0)
    );
  end component;
  signal shell_reset : std_logic := '0';
  signal win_addr    : std_logic_vector(6 downto 0) := (others => '0');
  signal win_wr      : std_logic := '0';
  signal win_rd      : std_logic := '0';
  signal win_wdata   : std_logic_vector(31 downto 0) := (others => '0');
  signal win_rdata   : std_logic_vector(31 downto 0) := (others => '0');

  type fifo_memory_t is array (0 to 15) of std_logic_vector(7 downto 0);
  signal fifo_memory : fifo_memory_t := (others => (others => '0'));
  signal read_pointer  : integer range 0 to 15 := 0;
  signal write_pointer : integer range 0 to 15 := 0;
  signal fifo_count    : integer range 0 to 16 := 0;
  signal threshold     : unsigned(4 downto 0) := to_unsigned(12, 5);
  signal push_error    : std_logic := '0';
  signal pop_error     : std_logic := '0';
  signal led_value     : std_logic_vector(15 downto 0) := (others => '0');
begin
  shell_reset <= not CPU_RESETN;
  LED <= led_value;

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT   => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID      => x"4649464F",
      BUILD_STAMP    => BUILD_STAMP
    )
    port map (
      clk       => CLK100MHZ,
      rst       => shell_reset,
      uart_rx   => UART_TXD_IN,
      uart_tx   => UART_RXD_OUT,
      win_addr  => win_addr,
      win_wr    => win_wr,
      win_rd    => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata
    );

  process (CLK100MHZ)
    variable next_count : integer range 0 to 16;
    variable read_value : std_logic_vector(31 downto 0);
    variable addr_value : natural range 0 to 127;
  begin
    if rising_edge(CLK100MHZ) then
      if CPU_RESETN = '0' then
        fifo_memory <= (others => (others => '0'));
        read_pointer <= 0;
        write_pointer <= 0;
        fifo_count <= 0;
        threshold <= to_unsigned(12, threshold'length);
        push_error <= '0';
        pop_error <= '0';
        win_rdata <= (others => '0');
      else
        next_count := fifo_count;
        read_value := (others => '0');
        addr_value := to_integer(unsigned(win_addr));

        if win_wr = '1' then
          case addr_value is
            when 0 =>
              if fifo_count < 16 then
                fifo_memory(write_pointer) <= win_wdata(7 downto 0);
                if write_pointer = 15 then
                  write_pointer <= 0;
                else
                  write_pointer <= write_pointer + 1;
                end if;
                next_count := next_count + 1;
              else
                push_error <= '1';
              end if;
            when 20 =>
              threshold <= unsigned(win_wdata(4 downto 0));
            when 24 =>
              if win_wdata(0) = '1' then
                push_error <= '0';
              end if;
              if win_wdata(1) = '1' then
                pop_error <= '0';
              end if;
            when others =>
              null;
          end case;
        end if;

        if win_rd = '1' then
          case addr_value is
            when 0 =>
              null;
            when 4 =>
              if fifo_count > 0 then
                read_value(7 downto 0) := fifo_memory(read_pointer);
                if read_pointer = 15 then
                  read_pointer <= 0;
                else
                  read_pointer <= read_pointer + 1;
                end if;
                next_count := next_count - 1;
              else
                pop_error <= '1';
              end if;
            when 8 =>
              if fifo_count > 0 then
                read_value(7 downto 0) := fifo_memory(read_pointer);
              end if;
            when 12 =>
              read_value(4 downto 0) := std_logic_vector(to_unsigned(fifo_count, 5));
            when 16 =>
              if fifo_count = 0 then
                read_value(0) := '1';
              end if;
              if fifo_count = 16 then
                read_value(1) := '1';
              end if;
              if to_unsigned(fifo_count, 5) >= threshold then
                read_value(2) := '1';
              end if;
            when 20 =>
              read_value(4 downto 0) := std_logic_vector(threshold);
            when 24 =>
              read_value(0) := push_error;
              read_value(1) := pop_error;
            when others =>
              null;
          end case;
        end if;

        fifo_count <= next_count;
        win_rdata <= read_value;
      end if;
    end if;
  end process;

  process (all)
    variable bar : std_logic_vector(15 downto 0);
  begin
    bar := (others => '0');
    for i in 0 to 15 loop
      if fifo_count > i then
        bar(i) := '1';
      end if;
    end loop;
    led_value <= bar;
  end process;
end architecture rtl;
