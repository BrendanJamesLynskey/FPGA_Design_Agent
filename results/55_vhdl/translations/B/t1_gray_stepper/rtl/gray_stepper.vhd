library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity gray_stepper is
    generic (
        DEBOUNCE_CYCLES : integer := 1_000_000;
        TICK_CYCLES     : integer := 100_000
    );
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        btn       : in  std_logic;
        dir_async : in  std_logic;
        led       : out std_logic_vector(15 downto 0);
        win_addr  : in  std_logic_vector(6 downto 0);
        win_wr    : in  std_logic;
        win_rd    : in  std_logic;
        win_wdata : in  std_logic_vector(31 downto 0);
        win_rdata : out std_logic_vector(31 downto 0)
    );
end entity gray_stepper;

architecture rtl of gray_stepper is
    function clog2(n : positive) return positive is
        variable v    : natural := n - 1;
        variable bits : natural := 0;
    begin
        while v > 0 loop
            bits := bits + 1;
            v := v / 2;
        end loop;

        if bits = 0 then
            return 1;
        else
            return bits;
        end if;
    end function;

    constant R_GRAY : std_logic_vector(6 downto 0) := "0000000";
    constant R_BIN  : std_logic_vector(6 downto 0) := "0000001";
    constant R_CTRL : std_logic_vector(6 downto 0) := "0000010";
    constant R_RATE : std_logic_vector(6 downto 0) := "0000011";
    constant R_STEPS: std_logic_vector(6 downto 0) := "0000100";
    constant PW     : positive := clog2(TICK_CYCLES + 1);

    signal lvl       : std_logic := '0';
    signal press     : std_logic := '0';
    signal dir       : std_logic := '0';
    signal auto_on   : std_logic := '0';
    signal astep     : std_logic;
    signal step      : std_logic;
    signal run_auto  : std_logic;

    signal bin       : unsigned(9 downto 0) := (others => '0');
    signal gray      : std_logic_vector(9 downto 0) := (others => '0');
    signal bin_nx    : unsigned(9 downto 0);
    signal rate      : unsigned(15 downto 0) := to_unsigned(250, 16);
    signal tk        : unsigned(15 downto 0) := (others => '0');
    signal steps     : unsigned(15 downto 0) := (others => '0');
    signal pre       : unsigned(PW - 1 downto 0) := (others => '0');
    signal win_rdata_reg : std_logic_vector(31 downto 0) := (others => '0');

    signal wr_bin  : std_logic;
    signal wr_ctrl : std_logic;
    signal wr_rate : std_logic;
begin
    u_db : entity work.bm_debounce
        generic map (
            CYCLES => DEBOUNCE_CYCLES
        )
        port map (
            clk     => clk,
            rst     => rst,
            d_async => btn,
            level   => lvl,
            rise    => press
        );

    u_dir : entity work.sync2_vh
        port map (
            clk => clk,
            rst => rst,
            d   => dir_async,
            q   => dir
        );

    wr_bin  <= '1' when win_wr = '1' and win_addr = R_BIN  else '0';
    wr_ctrl <= '1' when win_wr = '1' and win_addr = R_CTRL else '0';
    wr_rate <= '1' when win_wr = '1' and win_addr = R_RATE else '0';

    run_auto <= '1' when auto_on = '1' and rate /= to_unsigned(0, 16) else '0';

    astep <= '1' when
        run_auto = '1' and
        wr_ctrl = '0' and
        wr_rate = '0' and
        pre = to_unsigned(TICK_CYCLES - 1, PW) and
        tk = rate - to_unsigned(1, 16)
        else '0';

    step <= press or astep;

    bin_nx <= bin - to_unsigned(1, 10) when dir = '1'
              else bin + to_unsigned(1, 10);

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                pre     <= (others => '0');
                tk      <= (others => '0');
                auto_on <= '0';
                rate    <= to_unsigned(250, 16);
            else
                if wr_ctrl = '1' then
                    auto_on <= win_wdata(0);
                end if;

                if wr_rate = '1' then
                    rate <= unsigned(win_wdata(15 downto 0));
                end if;

                if wr_ctrl = '1' or wr_rate = '1' or run_auto = '0' then
                    pre <= (others => '0');
                    tk  <= (others => '0');
                elsif pre = to_unsigned(TICK_CYCLES - 1, PW) then
                    pre <= (others => '0');

                    if tk = rate - to_unsigned(1, 16) then
                        tk <= (others => '0');
                    else
                        tk <= tk + to_unsigned(1, 16);
                    end if;
                else
                    pre <= pre + to_unsigned(1, PW);
                end if;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                bin   <= (others => '0');
                gray  <= (others => '0');
                steps <= (others => '0');
            elsif wr_bin = '1' then
                bin  <= unsigned(win_wdata(9 downto 0));
                gray <= win_wdata(9 downto 0) xor
                        ('0' & win_wdata(9 downto 1));
            elsif step = '1' then
                bin   <= bin_nx;
                gray  <= std_logic_vector(bin_nx xor ('0' & bin_nx(9 downto 1)));
                steps <= steps + to_unsigned(1, 16);
            end if;
        end if;
    end process;

    led <= auto_on & "00000" & gray;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                win_rdata_reg <= (others => '0');
            elsif win_rd = '1' then
                case win_addr is
                    when R_GRAY =>
                        win_rdata_reg <= (31 downto 10 => '0') & gray;
                    when R_BIN =>
                        win_rdata_reg <= (31 downto 10 => '0') & std_logic_vector(bin);
                    when R_CTRL =>
                        win_rdata_reg <= (31 downto 9 => '0') & dir & "0000000" & auto_on;
                    when R_RATE =>
                        win_rdata_reg <= (31 downto 16 => '0') & std_logic_vector(rate);
                    when R_STEPS =>
                        win_rdata_reg <= (31 downto 16 => '0') & std_logic_vector(steps);
                    when others =>
                        win_rdata_reg <= (others => '0');
                end case;
            end if;
        end if;
    end process;

    win_rdata <= win_rdata_reg;
end architecture rtl;
