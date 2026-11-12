library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cdcfx_c10 is
    port (
        clk_a  : in  std_logic;
        clk_b  : in  std_logic;
        rst    : in  std_logic;
        winc   : in  std_logic;
        wdata  : in  std_logic_vector(15 downto 0);
        wfull  : out std_logic;
        rinc   : in  std_logic;
        rdata  : out std_logic_vector(15 downto 0);
        rempty : out std_logic
    );
end entity cdcfx_c10;

architecture rtl of cdcfx_c10 is
    type mem_t is array (0 to 15) of std_logic_vector(15 downto 0);
    signal mem : mem_t;

    signal wbin       : std_logic_vector(4 downto 0) := (others => '0');
    signal wptr       : std_logic_vector(4 downto 0) := (others => '0');
    signal rbin       : std_logic_vector(4 downto 0) := (others => '0');
    signal rptr       : std_logic_vector(4 downto 0) := (others => '0');

    signal wq1        : std_logic_vector(4 downto 0) := (others => '0');
    signal wq2        : std_logic_vector(4 downto 0) := (others => '0');
    signal rq1        : std_logic_vector(4 downto 0) := (others => '0');
    signal rq2        : std_logic_vector(4 downto 0) := (others => '0');

    signal full       : std_logic := '0';
    signal empty      : std_logic := '1';

    signal wbin_next  : std_logic_vector(4 downto 0);
    signal wgray_next : std_logic_vector(4 downto 0);
    signal rbin_next  : std_logic_vector(4 downto 0);
    signal rgray_next : std_logic_vector(4 downto 0);

    signal rd_q       : std_logic_vector(15 downto 0) := (others => '0');

    attribute ASYNC_REG : string;
    attribute ASYNC_REG of wq1 : signal is "TRUE";
    attribute ASYNC_REG of wq2 : signal is "TRUE";
    attribute ASYNC_REG of rq1 : signal is "TRUE";
    attribute ASYNC_REG of rq2 : signal is "TRUE";
begin
    wbin_next <= std_logic_vector(unsigned(wbin) + 1)
                 when winc = '1' and full = '0' else wbin;
    wgray_next <= std_logic_vector(shift_right(unsigned(wbin_next), 1) xor unsigned(wbin_next));

    rbin_next <= std_logic_vector(unsigned(rbin) + 1)
                 when rinc = '1' and empty = '0' else rbin;
    rgray_next <= std_logic_vector(shift_right(unsigned(rbin_next), 1) xor unsigned(rbin_next));

    process (clk_a)
    begin
        if rising_edge(clk_a) then
            wq1 <= rptr;
            wq2 <= wq1;
        end if;
    end process;

    process (clk_b)
    begin
        if rising_edge(clk_b) then
            rq1 <= wptr;
            rq2 <= rq1;
        end if;
    end process;

    process (clk_a)
    begin
        if rising_edge(clk_a) then
            wbin <= wbin_next;
            wptr <= wgray_next;

            if wgray_next = ((not wq2(4 downto 3)) & wq2(2 downto 0)) then
                full <= '1';
            else
                full <= '0';
            end if;

            if winc = '1' and full = '0' then
                mem(to_integer(unsigned(wbin(3 downto 0)))) <= wdata;
            end if;
        end if;
    end process;

    process (clk_b)
    begin
        if rising_edge(clk_b) then
            rbin <= rbin_next;
            rptr <= rgray_next;

            if rgray_next = rq2 then
                empty <= '1';
            else
                empty <= '0';
            end if;

            if rinc = '1' and empty = '0' then
                rd_q <= mem(to_integer(unsigned(rbin(3 downto 0))));
            end if;
        end if;
    end process;

    wfull  <= full;
    rempty <= empty;
    rdata  <= rd_q;
end architecture rtl;
