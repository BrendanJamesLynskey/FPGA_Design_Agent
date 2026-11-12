library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity elevator_fsm is
  generic (
    FLOOR_CYCLES : integer := 150_000_000;
    DOOR_CYCLES  : integer := 200_000_000
  );
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    sw_async  : in  std_logic_vector(3 downto 0);
    led       : out std_logic_vector(15 downto 0);
    win_addr  : in  std_logic_vector(6 downto 0);
    win_wr    : in  std_logic;
    win_rd    : in  std_logic;
    win_wdata : in  std_logic_vector(31 downto 0);
    win_rdata : out std_logic_vector(31 downto 0)
  );
end entity elevator_fsm;

architecture rtl of elevator_fsm is
  component sync2 is
    generic (
      WIDTH : integer := 1
    );
    port (
      clk : in  std_logic;
      rst : in  std_logic;
      d   : in  std_logic_vector(WIDTH - 1 downto 0);
      q   : out std_logic_vector(WIDTH - 1 downto 0)
    );
  end component;

  constant R_FLOOR : std_logic_vector(6 downto 0) := "0000000";
  constant R_DIR   : std_logic_vector(6 downto 0) := "0000001";
  constant R_PEND  : std_logic_vector(6 downto 0) := "0000010";
  constant R_STATE : std_logic_vector(6 downto 0) := "0000011";
  constant R_MOVES : std_logic_vector(6 downto 0) := "0000100";

  constant IDLE   : std_logic_vector(1 downto 0) := "00";
  constant MOVING : std_logic_vector(1 downto 0) := "01";
  constant DOOR   : std_logic_vector(1 downto 0) := "10";

  signal sw        : std_logic_vector(3 downto 0) := (others => '0');
  signal sw_q      : std_logic_vector(3 downto 0) := (others => '0');
  signal pend      : std_logic_vector(3 downto 0) := (others => '0');
  signal calls     : std_logic_vector(3 downto 0) := (others => '0');
  signal p1        : std_logic_vector(3 downto 0) := (others => '0');
  signal above     : std_logic_vector(3 downto 0) := (others => '0');
  signal below     : std_logic_vector(3 downto 0) := (others => '0');
  signal state     : std_logic_vector(1 downto 0) := IDLE;
  signal floor     : unsigned(1 downto 0) := (others => '0');
  signal nf        : unsigned(1 downto 0) := (others => '0');
  signal dir       : std_logic := '0';
  signal moves     : unsigned(15 downto 0) := (others => '0');
  signal timer     : unsigned(31 downto 0) := (others => '0');
  signal led_reg   : std_logic_vector(15 downto 0) := (others => '0');
  signal rdata_reg : std_logic_vector(31 downto 0) := (others => '0');

  signal ahead_up : std_logic;
  signal ahead_dn : std_logic;
begin
  u_sw : sync2
    generic map (
      WIDTH => 4
    )
    port map (
      clk => clk,
      rst => rst,
      d   => sw_async,
      q   => sw
    );

  process (all)
    variable calls_v : std_logic_vector(3 downto 0);
    variable p1_v    : std_logic_vector(3 downto 0);
    variable above_v : std_logic_vector(3 downto 0);
    variable below_v : std_logic_vector(3 downto 0);
  begin
    calls_v := sw and not sw_q;

    if win_wr = '1' and win_addr = R_PEND then
      calls_v := calls_v or win_wdata(3 downto 0);
    end if;

    if state = DOOR then
      calls_v(to_integer(floor)) := '0';
    end if;

    p1_v := pend or calls_v;
    above_v := (others => '0');
    below_v := (others => '0');

    for k in 0 to 3 loop
      if k > to_integer(floor) then
        above_v(k) := '1';
      end if;
      if k < to_integer(floor) then
        below_v(k) := '1';
      end if;
    end loop;

    calls <= calls_v;
    p1    <= p1_v;
    above <= above_v;
    below <= below_v;
  end process;

  ahead_up <= '1' when (p1 and above) /= "0000" else '0';
  ahead_dn <= '1' when (p1 and below) /= "0000" else '0';

  nf <= floor - to_unsigned(1, floor'length) when dir = '1' else
        floor + to_unsigned(1, floor'length);

  process (clk)
    variable pend_v : std_logic_vector(3 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        sw_q  <= (others => '0');
        pend  <= (others => '0');
        state <= IDLE;
        floor <= (others => '0');
        dir   <= '0';
        moves <= (others => '0');
        timer <= (others => '0');
      else
        sw_q  <= sw;
        pend_v := p1;
        pend  <= p1;
        timer <= timer + 1;

        if state = MOVING and timer = to_unsigned(FLOOR_CYCLES - 1, 32) then
          floor <= nf;
          moves <= moves + 1;
          timer <= (others => '0');

          if p1(to_integer(nf)) = '1' then
            pend_v(to_integer(nf)) := '0';
            pend <= pend_v;
            state <= DOOR;
          end if;
        elsif state = IDLE or
              (state = DOOR and timer = to_unsigned(DOOR_CYCLES - 1, 32)) then
          timer <= (others => '0');

          if p1(to_integer(floor)) = '1' then
            pend_v(to_integer(floor)) := '0';
            pend <= pend_v;
            state <= DOOR;
          elsif (dir = '1' and ahead_dn = '1') or
                (dir = '0' and ahead_up = '1') then
            state <= MOVING;
          elsif (dir = '1' and ahead_up = '1') or
                (dir = '0' and ahead_dn = '1') then
            dir   <= not dir;
            state <= MOVING;
          else
            state <= IDLE;
          end if;
        end if;
      end if;
    end if;
  end process;

  process (clk)
    variable floor_leds : unsigned(3 downto 0);
    variable led_v      : std_logic_vector(15 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led_reg <= (others => '0');
      else
        floor_leds := shift_left(to_unsigned(1, 4), to_integer(floor));
        led_v := (others => '0');

        if state = DOOR then
          led_v(15) := '1';
        end if;
        if state = MOVING then
          led_v(14) := '1';
        end if;

        led_v(7 downto 4) := pend;
        led_v(3 downto 0) := std_logic_vector(floor_leds);
        led_reg <= led_v;
      end if;
    end if;
  end process;

  process (clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        rdata_reg <= (others => '0');
      elsif win_rd = '1' then
        case win_addr is
          when R_FLOOR =>
            rdata_reg <= (others => '0');
            rdata_reg(1 downto 0) <= std_logic_vector(floor);
          when R_DIR =>
            rdata_reg <= (others => '0');
            rdata_reg(0) <= dir;
          when R_PEND =>
            rdata_reg <= (others => '0');
            rdata_reg(3 downto 0) <= pend;
          when R_STATE =>
            rdata_reg <= (others => '0');
            rdata_reg(1 downto 0) <= state;
          when R_MOVES =>
            rdata_reg <= (others => '0');
            rdata_reg(15 downto 0) <= std_logic_vector(moves);
          when others =>
            rdata_reg <= (others => '0');
        end case;
      end if;
    end if;
  end process;

  led       <= led_reg;
  win_rdata <= rdata_reg;
end architecture rtl;
