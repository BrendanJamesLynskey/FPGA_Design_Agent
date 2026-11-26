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
        variable value  : natural := n - 1;
        variable result : natural := 0;
    begin
        while value > 0 loop
            value  := value / 2;
            result := result + 1;
        end loop;
        if result = 0 then
            return 1;
        else
            return result;
        end if;
    end function;

    -- True when exactly one bit of x is set (what PSL's onehot() says; GHDL's simulator has no onehot, so the property calls this function)
    function onebit(x : unsigned) return boolean is
        variable n : natural := 0;
    begin
        for i in x'range loop
            if x(i) = '1' then
                n := n + 1;
            end if;
        end loop;
        return n = 1;
    end function;

    constant PW : positive := clog2(TICK_CYCLES + 1);

    constant R_GRAY  : std_logic_vector(6 downto 0) := "0000000";
    constant R_BIN   : std_logic_vector(6 downto 0) := "0000001";
    constant R_CTRL  : std_logic_vector(6 downto 0) := "0000010";
    constant R_RATE  : std_logic_vector(6 downto 0) := "0000011";
    constant R_STEPS : std_logic_vector(6 downto 0) := "0000100";

    signal lvl       : std_logic;
    signal press     : std_logic;
    signal dir       : std_logic;
    signal auto_on   : std_logic;
    signal run       : std_logic;
    signal astep     : std_logic;
    signal step      : std_logic;

    signal bin       : unsigned(9 downto 0);
    signal gray      : unsigned(9 downto 0);
    signal bin_nx    : unsigned(9 downto 0);

    signal rate      : unsigned(15 downto 0);
    signal tk        : unsigned(15 downto 0);
    signal steps     : unsigned(15 downto 0);
    signal pre       : unsigned(PW - 1 downto 0);

    signal gray_q    : unsigned(9 downto 0);          -- monitor registers for the PSL properties: last clock's gray and steps
    signal steps_q   : unsigned(15 downto 0);        -- (GHDL's simulator has no prev(); the registers say the same thing in plain VHDL)
    signal wr_bin    : std_logic;
    signal wr_ctrl   : std_logic;
    signal wr_rate   : std_logic;
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

    u_dir : entity work.sync2
        port map (
            clk => clk,
            rst => rst,
            d   => dir_async,
            q   => dir
        );

    wr_bin  <= '1' when win_wr = '1' and win_addr = R_BIN  else '0';
    wr_ctrl <= '1' when win_wr = '1' and win_addr = R_CTRL else '0';
    wr_rate <= '1' when win_wr = '1' and win_addr = R_RATE else '0';

    run <= '1' when auto_on = '1' and rate /= to_unsigned(0, 16) else '0';

    astep <= '1'
        when run = '1'
         and wr_ctrl = '0'
         and wr_rate = '0'
         and pre = to_unsigned(TICK_CYCLES - 1, PW)
         and tk = rate - to_unsigned(1, 16)
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

                if wr_ctrl = '1' or wr_rate = '1' or run = '0' then
                    pre <= (others => '0');
                    tk  <= (others => '0');
                elsif pre = to_unsigned(TICK_CYCLES - 1, PW) then
                    pre <= (others => '0');
                    if tk = rate - to_unsigned(1, 16) then
                        tk <= (others => '0');
                    else
                        tk <= tk + 1;
                    end if;
                else
                    pre <= pre + 1;
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
                gray <= unsigned(win_wdata(9 downto 0))
                        xor shift_right(unsigned(win_wdata(9 downto 0)), 1);
            elsif step = '1' then
                bin   <= bin_nx;
                gray  <= bin_nx xor shift_right(bin_nx, 1);
                steps <= steps + 1;
            end if;
        end if;
    end process;

    led <= auto_on & "00000" & std_logic_vector(gray);

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                win_rdata <= (others => '0');
            elsif win_rd = '1' then
                case win_addr is
                    when R_GRAY =>
                        win_rdata <= std_logic_vector(resize(gray, 32));
                    when R_BIN =>
                        win_rdata <= std_logic_vector(resize(bin, 32));
                    when R_CTRL =>
                        win_rdata <= (31 downto 9 => '0') & dir & "0000000" & auto_on;
                    when R_RATE =>
                        win_rdata <= std_logic_vector(resize(rate, 32));
                    when R_STEPS =>
                        win_rdata <= std_logic_vector(resize(steps, 32));
                    when others =>
                        win_rdata <= (others => '0');
                end case;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            gray_q  <= gray;
            steps_q <= steps;
        end if;
    end process;

    -- Properties of the SystemVerilog twin (benchmark/tasks/t1_gray_stepper/ref/rtl/gray_stepper.sv, `ifdef FORMAL`), in PSL.
    -- psl default clock is rising_edge(clk);
    -- Formal start: the first cycle is a reset cycle (an assumption for the proof only; the SV side puts the same assumption in its wrapper).
    -- psl assume_reset_first : assume rst = '1';
    -- REQ-01: a step (no BIN write, no reset) changes exactly one bit of the Gray register (SV: $countones(gray ^ $past(gray)) == 1).
    -- psl req01_one_bit : assert always ((rst = '0' and step = '1' and wr_bin = '0') -> next (onebit(gray xor gray_q)));
    -- Invariant: the Gray register is the Gray code of the binary register, outside reset (SV: rst || gray == (bin ^ (bin >> 1))).
    -- psl inv_gray_of_bin : assert always (rst = '1' or gray = (bin xor ('0' & bin(9 downto 1))));
    -- Reset values: the cycle after a reset, BIN, STEPS and the auto flag are cleared and RATE is 250 (spec.yaml reset.effect).
    -- psl reset_values : assert always ((rst = '1') -> next (bin = 0 and steps = 0 and auto_on = '0' and rate = 250));
    -- Every step that is not a BIN write counts: STEPS advances by one (modulo 2**16) (SV twin: no such assertion; added here for both).
    -- psl steps_count : assert always ((rst = '0' and step = '1' and wr_bin = '0') -> next (steps = steps_q + 1));
    -- Brief 202 (143c rigour): the GHDL plugin adds `<label>.cover` beside each implication (the cover of its left side); the invariant has no
    -- left side, so its antecedent is written out: the state in which it could be broken is outside reset.
    -- psl inv_gray_of_bin_ante : cover {rst = '0'};
    -- Cover: a step happens, and the binary count wraps from 1023 to 0 going up.
    -- psl cov_step : cover {rst = '0' and step = '1' and wr_bin = '0'};
    -- psl cov_wrap : cover {bin = 1023 and step = '1' and dir = '0' and wr_bin = '0' and rst = '0'; bin = 0};
end architecture rtl;
