library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1_elevator_fsm_top is
  generic (
    CLKS_PER_BIT   : integer := 868;
    TIMEOUT_CYCLES : integer := 100000000;
    BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000";
    FLOOR_CYCLES   : integer := 100000000;
    DOOR_CYCLES    : integer := 300000000
  );
  port (
    CLK100MHZ   : in  std_logic;
    CPU_RESETN  : in  std_logic;
    SW          : in  std_logic_vector(15 downto 0);
    LED         : out std_logic_vector(15 downto 0);
    UART_TXD_IN : in  std_logic;
    UART_RXD_OUT: out std_logic
  );
end entity;

architecture rtl of t1_elevator_fsm_top is
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

  type service_state_t is (IDLE, MOVING, DOOR_OPEN);
  signal rst             : std_logic := '1';
  signal sw_meta         : std_logic_vector(3 downto 0) := (others => '0');
  signal sw_sync         : std_logic_vector(3 downto 0) := (others => '0');
  signal sw_previous     : std_logic_vector(3 downto 0) := (others => '0');
  signal calls           : std_logic_vector(3 downto 0) := (others => '0');
  signal floor_q         : integer range 0 to 3 := 0;
  signal direction_up    : std_logic := '1';
  signal service_state   : service_state_t := IDLE;
  signal travel_timer    : integer range 0 to FLOOR_CYCLES := 0;
  signal door_timer      : integer range 0 to DOOR_CYCLES := 0;
  signal travelled       : unsigned(31 downto 0) := (others => '0');
  signal win_addr        : std_logic_vector(6 downto 0);
  signal win_wr          : std_logic;
  signal win_rd          : std_logic;
  signal win_wdata       : std_logic_vector(31 downto 0);
  signal win_rdata       : std_logic_vector(31 downto 0) := (others => '0');
begin
  -- The board reset is synchronous as required by the specification.
  rst <= not CPU_RESETN;

  process (CLK100MHZ)
  begin
    if rising_edge(CLK100MHZ) then
      if rst = '1' then
        sw_meta <= (others => '0');
        sw_sync <= (others => '0');
      else
        sw_meta <= SW(3 downto 0);
        sw_sync <= sw_meta;
      end if;
    end if;
  end process;

  u_shell : fpga_shell
    generic map (
      CLKS_PER_BIT => CLKS_PER_BIT,
      TIMEOUT_CYCLES => TIMEOUT_CYCLES,
      DESIGN_ID => x"454C4556",
      BUILD_STAMP => BUILD_STAMP
    )
    port map (
      clk => CLK100MHZ, rst => rst, uart_rx => UART_TXD_IN,
      uart_tx => UART_RXD_OUT, win_addr => win_addr, win_wr => win_wr,
      win_rd => win_rd, win_wdata => win_wdata, win_rdata => win_rdata
    );

  process (CLK100MHZ)
    variable calls_v       : std_logic_vector(3 downto 0);
    variable dest_floor    : integer range 0 to 3;
    variable dir_v         : std_logic;
    variable below_found   : boolean;
    variable above_found   : boolean;
    variable nearest_below: integer range 0 to 3;
    variable nearest_above: integer range 0 to 3;
    variable up_distance   : integer range 0 to 3;
    variable down_distance : integer range 0 to 3;
    variable reg_value     : std_logic_vector(31 downto 0);
  begin
    if rising_edge(CLK100MHZ) then
      if rst = '1' then
        sw_previous   <= (others => '0');
        calls         <= (others => '0');
        floor_q       <= 0;
        direction_up  <= '1';
        service_state <= IDLE;
        travel_timer  <= 0;
        door_timer    <= 0;
        travelled     <= (others => '0');
        win_rdata     <= (others => '0');
      else
        calls_v := calls;
        for i in 0 to 3 loop
          if sw_sync(i) = '1' and sw_previous(i) = '0' then
            calls_v(i) := '1';
          end if;
        end loop;
        if win_wr = '1' and win_addr = "0010000" then
          for i in 0 to 3 loop
            if win_wdata(i) = '1' then
              calls_v(i) := '1';
            end if;
          end loop;
        end if;
        sw_previous <= sw_sync;

        case service_state is
          when IDLE =>
            travel_timer <= 0;
            if calls_v(floor_q) = '1' then
              service_state <= DOOR_OPEN;
              if DOOR_CYCLES > 1 then door_timer <= DOOR_CYCLES; else door_timer <= 1; end if;
            elsif calls_v /= "0000" then
              below_found := false;
              above_found := false;
              nearest_below := 0;
              nearest_above := 3;
              for i in 0 to 3 loop
                if calls_v(i) = '1' then
                  if i < floor_q then
                    if (not below_found) or i > nearest_below then nearest_below := i; end if;
                    below_found := true;
                  elsif i > floor_q then
                    if (not above_found) or i < nearest_above then nearest_above := i; end if;
                    above_found := true;
                  end if;
                end if;
              end loop;
              if not below_found then
                dir_v := '1';
              elsif not above_found then
                dir_v := '0';
              else
                down_distance := floor_q - nearest_below;
                up_distance := nearest_above - floor_q;
                if up_distance <= down_distance then dir_v := '1'; else dir_v := '0'; end if;
              end if;
              direction_up <= dir_v;
              if (dir_v = '1' and floor_q < 3) or (dir_v = '0' and floor_q > 0) then
                service_state <= MOVING;
                if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
              end if;
            end if;

          when MOVING =>
            if travel_timer <= 1 then
              travel_timer <= 0;
              if direction_up = '1' then dest_floor := floor_q + 1; else dest_floor := floor_q - 1; end if;
              floor_q <= dest_floor;
              travelled <= travelled + 1;
              if calls_v(dest_floor) = '1' then
                service_state <= DOOR_OPEN;
                if DOOR_CYCLES > 1 then door_timer <= DOOR_CYCLES; else door_timer <= 1; end if;
              else
                below_found := false;
                above_found := false;
                if direction_up = '1' then
                  for i in 0 to 3 loop
                    if i > dest_floor and calls_v(i) = '1' then above_found := true; end if;
                    if i < dest_floor and calls_v(i) = '1' then below_found := true; end if;
                  end loop;
                  if above_found then
                    service_state <= MOVING;
                    if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                  elsif below_found then
                    direction_up <= '0';
                    service_state <= MOVING;
                    if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                  else
                    service_state <= IDLE;
                  end if;
                else
                  for i in 0 to 3 loop
                    if i < dest_floor and calls_v(i) = '1' then below_found := true; end if;
                    if i > dest_floor and calls_v(i) = '1' then above_found := true; end if;
                  end loop;
                  if below_found then
                    service_state <= MOVING;
                    if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                  elsif above_found then
                    direction_up <= '1';
                    service_state <= MOVING;
                    if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                  else
                    service_state <= IDLE;
                  end if;
                end if;
              end if;
            else
              travel_timer <= travel_timer - 1;
            end if;

          when DOOR_OPEN =>
            if door_timer <= 1 then
              door_timer <= 0;
              calls_v(floor_q) := '0';
              below_found := false;
              above_found := false;
              if direction_up = '1' then
                for i in 0 to 3 loop
                  if i > floor_q and calls_v(i) = '1' then above_found := true; end if;
                  if i < floor_q and calls_v(i) = '1' then below_found := true; end if;
                end loop;
                if above_found then
                  service_state <= MOVING;
                  if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                elsif below_found then
                  direction_up <= '0';
                  service_state <= MOVING;
                  if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                else
                  service_state <= IDLE;
                end if;
              else
                for i in 0 to 3 loop
                  if i < floor_q and calls_v(i) = '1' then below_found := true; end if;
                  if i > floor_q and calls_v(i) = '1' then above_found := true; end if;
                end loop;
                if below_found then
                  service_state <= MOVING;
                  if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                elsif above_found then
                  direction_up <= '1';
                  service_state <= MOVING;
                  if FLOOR_CYCLES > 1 then travel_timer <= FLOOR_CYCLES; else travel_timer <= 1; end if;
                else
                  service_state <= IDLE;
                end if;
              end if;
            else
              door_timer <= door_timer - 1;
            end if;
        end case;

        calls <= calls_v;
        case win_addr is
          when "0000000" => reg_value := x"454C4556";
          when "0000100" =>
            reg_value := (others => '0');
            reg_value(1 downto 0) := std_logic_vector(to_unsigned(floor_q, 2));
            reg_value(2) := direction_up;
            if service_state = MOVING then reg_value(3) := '1'; end if;
            if service_state = DOOR_OPEN then reg_value(4) := '1'; end if;
          when "0001000" => reg_value := (31 downto 4 => '0') & calls_v;
          when "0001100" => reg_value := std_logic_vector(travelled);
          when "0010000" => reg_value := (others => '0');
          when others => reg_value := (others => '0');
        end case;
        if win_rd = '1' then win_rdata <= reg_value; end if;
      end if;
    end if;
  end process;

  process (all)
    variable led_v : std_logic_vector(15 downto 0);
  begin
    led_v := (others => '0');
    led_v(floor_q) := '1';
    led_v(7 downto 4) := calls;
    if service_state = MOVING then led_v(14) := '1'; end if;
    if service_state = DOOR_OPEN then led_v(15) := '1'; end if;
    LED <= led_v;
  end process;
end architecture;
