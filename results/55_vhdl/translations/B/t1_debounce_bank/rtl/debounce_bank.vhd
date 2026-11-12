library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity debounce_bank is
    generic (
        DEBOUNCE_CYCLES : integer := 2_000_000
    );
    port (
        clk       : in  std_logic;
        rst       : in  std_logic;
        sw_async  : in  std_logic_vector(15 downto 0);
        led       : out std_logic_vector(15 downto 0);
        win_addr  : in  std_logic_vector(6 downto 0);
        win_wr    : in  std_logic;
        win_rd    : in  std_logic;
        win_wdata : in  std_logic_vector(31 downto 0);
        win_rdata : out std_logic_vector(31 downto 0)
    );
end entity debounce_bank;

architecture rtl of debounce_bank is
    constant R_LEVEL : std_logic_vector(6 downto 0) := "0000000";
    constant R_EDGES : std_logic_vector(6 downto 0) := "0000001";
    constant R_RISE  : std_logic_vector(6 downto 0) := "0000010";
    constant R_FALL  : std_logic_vector(6 downto 0) := "0000011";

    type count_array_t is array (0 to 15) of unsigned(7 downto 0);

    signal lvl       : std_logic_vector(15 downto 0) := (others => '0');
    signal lvl_d     : std_logic_vector(15 downto 0) := (others => '0');
    signal rise_vec  : std_logic_vector(15 downto 0);
    signal fall_vec  : std_logic_vector(15 downto 0);
    signal edges     : std_logic_vector(15 downto 0) := (others => '0');
    signal rise_en   : std_logic_vector(15 downto 0) := (others => '1');
    signal fall_en   : std_logic_vector(15 downto 0) := (others => '0');
    signal unused    : std_logic_vector(15 downto 0);
    signal cnt       : count_array_t := (others => (others => '0'));
    signal win_rdata_r : std_logic_vector(31 downto 0) := (others => '0');
begin
    g_db : for k in 0 to 15 generate
        u_db : entity work.bm_debounce
            generic map (
                CYCLES => DEBOUNCE_CYCLES
            )
            port map (
                clk     => clk,
                rst     => rst,
                d_async => sw_async(k),
                level   => lvl(k),
                rise    => unused(k)
            );
    end generate;

    rise_vec <= lvl and not lvl_d;
    fall_vec <= not lvl and lvl_d;
    led      <= lvl_d;
    win_rdata <= win_rdata_r;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                lvl_d   <= (others => '0');
                edges   <= (others => '0');
                rise_en <= (others => '1');
                fall_en <= (others => '0');
                cnt     <= (others => (others => '0'));
            else
                lvl_d <= lvl;

                if win_wr = '1' and win_addr = R_EDGES then
                    edges <= (edges and not win_wdata(15 downto 0))
                             or (rise_vec and rise_en)
                             or (fall_vec and fall_en);
                else
                    edges <= edges
                             or (rise_vec and rise_en)
                             or (fall_vec and fall_en);
                end if;

                if win_wr = '1' and win_addr = R_RISE then
                    rise_en <= win_wdata(15 downto 0);
                end if;

                if win_wr = '1' and win_addr = R_FALL then
                    fall_en <= win_wdata(15 downto 0);
                end if;

                for k in 0 to 15 loop
                    if win_wr = '1' and
                       win_addr = std_logic_vector(to_unsigned(4 + k / 4, 7)) then
                        cnt(k) <= (others => '0');
                    elsif lvl(k) /= lvl_d(k) then
                        cnt(k) <= cnt(k) + 1;
                    end if;
                end loop;
            end if;
        end if;
    end process;

    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                win_rdata_r <= (others => '0');
            elsif win_rd = '1' then
                case win_addr is
                    when R_LEVEL =>
                        win_rdata_r <= x"0000" & lvl_d;
                    when R_EDGES =>
                        win_rdata_r <= x"0000" & edges;
                    when R_RISE =>
                        win_rdata_r <= x"0000" & rise_en;
                    when R_FALL =>
                        win_rdata_r <= x"0000" & fall_en;
                    when "0000100" =>
                        win_rdata_r(31 downto 24) <= std_logic_vector(cnt(3));
                        win_rdata_r(23 downto 16) <= std_logic_vector(cnt(2));
                        win_rdata_r(15 downto 8)  <= std_logic_vector(cnt(1));
                        win_rdata_r(7 downto 0)   <= std_logic_vector(cnt(0));
                    when "0000101" =>
                        win_rdata_r(31 downto 24) <= std_logic_vector(cnt(7));
                        win_rdata_r(23 downto 16) <= std_logic_vector(cnt(6));
                        win_rdata_r(15 downto 8)  <= std_logic_vector(cnt(5));
                        win_rdata_r(7 downto 0)   <= std_logic_vector(cnt(4));
                    when "0000110" =>
                        win_rdata_r(31 downto 24) <= std_logic_vector(cnt(11));
                        win_rdata_r(23 downto 16) <= std_logic_vector(cnt(10));
                        win_rdata_r(15 downto 8)  <= std_logic_vector(cnt(9));
                        win_rdata_r(7 downto 0)   <= std_logic_vector(cnt(8));
                    when "0000111" =>
                        win_rdata_r(31 downto 24) <= std_logic_vector(cnt(15));
                        win_rdata_r(23 downto 16) <= std_logic_vector(cnt(14));
                        win_rdata_r(15 downto 8)  <= std_logic_vector(cnt(13));
                        win_rdata_r(7 downto 0)   <= std_logic_vector(cnt(12));
                    when others =>
                        win_rdata_r <= (others => '0');
                end case;
            end if;
        end if;
    end process;
end architecture rtl;
