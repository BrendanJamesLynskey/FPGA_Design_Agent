library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1_gray_stepper_top is
  generic (
    CLKS_PER_BIT   : integer := 868;
    TIMEOUT_CYCLES : integer := 100000000;
    BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000";
    DEBOUNCE_CYCLES : integer := 1000000;
    TICK_CYCLES     : integer := 100000
  );
  port (
    CLK100MHZ  : in  std_logic;
    CPU_RESETN : in  std_logic;
    BTNU       : in  std_logic;
    SW         : in  std_logic_vector(15 downto 0);
    LED        : out std_logic_vector(15 downto 0);
    UART_TXD_IN  : in  std_logic;
    UART_RXD_OUT : out std_logic
  );
end entity;

architecture rtl of t1_gray_stepper_top is
  component reset_sync is
    port (
      clk         : in  std_logic;
      rst_n_async : in  std_logic;
      rst         : out std_logic
    );
  end component;

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
  attribute box_type : string;
  attribute box_type of fpga_shell : component is "black_box";
  constant DESIGN_ID : std_logic_vector(31 downto 0) := x"47524159"; -- ASCII GRAY
  function positive_or_one(value : integer) return positive is
  begin
    if value < 1 then return 1; else return value; end if;
  end function;
  constant DEBOUNCE_LIMIT : positive := positive_or_one(DEBOUNCE_CYCLES);
  constant TICK_LIMIT : positive := positive_or_one(TICK_CYCLES);
  constant DB_WIDTH : positive := 32;
  constant TICK_WIDTH : positive := 32;

  signal rst : std_logic := '1';
  signal btn_meta : std_logic := '0';
  signal btn_sync : std_logic := '0';
  signal btn_last : std_logic := '0';
  signal btn_armed : std_logic := '1';
  signal db_count : unsigned(DB_WIDTH-1 downto 0) := (others => '0');
  signal binary_count : unsigned(9 downto 0) := (others => '0');
  signal step_count : unsigned(31 downto 0) := (others => '0');
  signal auto_enable : std_logic := '0';
  signal auto_rate : unsigned(31 downto 0) := (others => '0');
  signal tick_count : unsigned(TICK_WIDTH-1 downto 0) := (others => '0');
  signal elapsed_ms : unsigned(31 downto 0) := (others => '0');
  signal win_addr : std_logic_vector(6 downto 0);
  signal win_wr : std_logic;
  signal win_rd : std_logic;
  signal win_wdata : std_logic_vector(31 downto 0);
  signal win_rdata : std_logic_vector(31 downto 0) := (others => '0');
  signal win_rdata_reg : std_logic_vector(31 downto 0) := (others => '0');
  signal manual_step : std_logic := '0';
  signal auto_step : std_logic := '0';
begin
  u_reset_sync : reset_sync
    port map (clk => CLK100MHZ, rst_n_async => CPU_RESETN, rst => rst);

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID => DESIGN_ID,
      BUILD_STAMP => BUILD_STAMP
    )
    port map (
      clk => CLK100MHZ,
      rst => rst,
      uart_rx => UART_TXD_IN,
      uart_tx => UART_RXD_OUT,
      win_addr => win_addr,
      win_wr => win_wr,
      win_rd => win_rd,
      win_wdata => win_wdata,
      win_rdata => win_rdata
    );

  process(binary_count, auto_enable)
    variable gray_value : unsigned(9 downto 0);
  begin
    gray_value := binary_count xor ('0' & binary_count(9 downto 1));
    LED <= (others => '0');
    LED(9 downto 0) <= std_logic_vector(gray_value);
    LED(15) <= auto_enable;
  end process;

  process(CLK100MHZ)
    variable count_v : unsigned(9 downto 0);
    variable steps_v : unsigned(31 downto 0);
    variable auto_v : std_logic;
    variable rate_v : unsigned(31 downto 0);
    variable elapsed_v : unsigned(31 downto 0);
    variable tick_v : unsigned(TICK_WIDTH-1 downto 0);
    variable manual_v : std_logic;
    variable automatic_v : std_logic;
    variable step_n : natural range 0 to 2;
    variable down_v : boolean;
    variable config_changed : boolean;
  begin
    if rising_edge(CLK100MHZ) then
      if rst = '1' then
        btn_meta <= '0';
        btn_sync <= '0';
        btn_last <= '0';
        btn_armed <= '1';
        db_count <= (others => '0');
        binary_count <= (others => '0');
        step_count <= (others => '0');
        auto_enable <= '0';
        auto_rate <= (others => '0');
        tick_count <= (others => '0');
        elapsed_ms <= (others => '0');
        manual_step <= '0';
        auto_step <= '0';
        win_rdata_reg <= (others => '0');
      else
        -- Debounce the sampled board input. The input is sampled only on the
        -- system clock; the qualification counter rejects short transitions.
        btn_meta <= BTNU;
        btn_sync <= btn_meta;

        count_v := binary_count;
        steps_v := step_count;
        auto_v := auto_enable;
        rate_v := auto_rate;
        elapsed_v := elapsed_ms;
        tick_v := tick_count;
        manual_v := '0';
        automatic_v := '0';
        config_changed := false;

        -- One-cycle registered read response, as required by the shell window.
        if win_rd = '1' then
          case win_addr is
            when "0000000" => win_rdata_reg <= std_logic_vector(resize(binary_count, 32));
            when "0000100" => win_rdata_reg <= std_logic_vector(resize(binary_count xor ('0' & binary_count(9 downto 1)), 32));
            when "0001000" => win_rdata_reg <= (31 downto 1 => '0') & auto_enable;
            when "0001100" => win_rdata_reg <= std_logic_vector(auto_rate);
            when "0010000" => win_rdata_reg <= std_logic_vector(step_count);
            when others => win_rdata_reg <= (others => '0');
          end case;
        end if;

        if win_wr = '1' then
          case win_addr is
            when "0000000" => count_v := unsigned(win_wdata(9 downto 0));
            when "0001000" =>
              if auto_v /= win_wdata(0) then
                auto_v := win_wdata(0);
                config_changed := true;
              end if;
            when "0001100" =>
              if rate_v /= unsigned(win_wdata) then
                rate_v := unsigned(win_wdata);
                config_changed := true;
              end if;
            when others => null;
          end case;
        end if;

        -- Button debounce: qualify each stable level for the configured period.
        if BTNU /= btn_last then
          btn_last <= BTNU;
          db_count <= to_unsigned(1, DB_WIDTH);
        elsif db_count < to_unsigned(DEBOUNCE_LIMIT, DB_WIDTH) then
          db_count <= db_count + 1;
        end if;
        if BTNU = '1' and btn_armed = '1' and
           ((BTNU /= btn_last and DEBOUNCE_LIMIT <= 1) or
            (BTNU = btn_last and db_count >= to_unsigned(DEBOUNCE_LIMIT-1, DB_WIDTH))) then
          manual_v := '1';
          btn_armed <= '0';
        elsif BTNU = '0' and btn_armed = '0' and
              ((BTNU /= btn_last and DEBOUNCE_LIMIT <= 1) or
               (BTNU = btn_last and db_count >= to_unsigned(DEBOUNCE_LIMIT-1, DB_WIDTH))) then
          btn_armed <= '1';
        end if;

        if config_changed then
          tick_v := (others => '0');
          elapsed_v := (others => '0');
        elsif auto_v = '1' and rate_v /= 0 then
          if tick_v = to_unsigned(TICK_LIMIT-1, TICK_WIDTH) then
            tick_v := (others => '0');
            if elapsed_v >= rate_v - 1 then
              automatic_v := '1';
              elapsed_v := (others => '0');
            else
              elapsed_v := elapsed_v + 1;
            end if;
          else
            tick_v := tick_v + 1;
          end if;
        else
          tick_v := (others => '0');
          elapsed_v := (others => '0');
        end if;

        step_n := 0;
        if manual_v = '1' then step_n := step_n + 1; end if;
        if automatic_v = '1' then step_n := step_n + 1; end if;
        down_v := SW(15) = '1';
        if step_n /= 0 then
          if down_v then
            count_v := count_v - to_unsigned(step_n, 10);
          else
            count_v := count_v + to_unsigned(step_n, 10);
          end if;
          steps_v := steps_v + to_unsigned(step_n, 32);
        end if;

        binary_count <= count_v;
        step_count <= steps_v;
        auto_enable <= auto_v;
        auto_rate <= rate_v;
        tick_count <= tick_v;
        elapsed_ms <= elapsed_v;
        manual_step <= manual_v;
        auto_step <= automatic_v;
      end if;
    end if;
  end process;

  win_rdata <= win_rdata_reg;
end architecture;
