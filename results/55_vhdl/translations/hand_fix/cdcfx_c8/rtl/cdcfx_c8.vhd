library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cdcfx_c8 is
    port (
        clk_a  : in  std_logic;
        clk_b  : in  std_logic;
        send   : in  std_logic;
        din    : in  std_logic_vector(15 downto 0);
        busy   : out std_logic;
        dvalid : out std_logic;
        dout   : out std_logic_vector(15 downto 0)
    );
end entity cdcfx_c8;

architecture rtl of cdcfx_c8 is
    -- hand fix (brief 55, rule M2): the two output registers get a defined start, as every other register here has;
    -- VHDL's rising_edge does not fire on the 'U'-to-'1' step at time 0 that Verilog counts as a posedge
    signal dvalid_r : std_logic := '0';
    signal dout_r   : std_logic_vector(15 downto 0) := (others => '0');
    signal data  : std_logic_vector(15 downto 0) := (others => '0');
    signal req   : std_logic := '0';
    signal bsy   : std_logic := '0';
    signal ack_s : std_logic_vector(1 downto 0) := (others => '0');
    signal req_s : std_logic_vector(1 downto 0) := (others => '0');
    signal ack   : std_logic := '0';

    attribute ASYNC_REG : string;
    attribute ASYNC_REG of ack_s : signal is "TRUE";
    attribute ASYNC_REG of req_s : signal is "TRUE";
begin
    busy <= bsy;
    dvalid <= dvalid_r;
    dout <= dout_r;

    process (clk_a)
    begin
        if rising_edge(clk_a) then
            ack_s <= ack_s(0) & ack;

            if bsy = '0' then
                if send = '1' and ack_s(1) = '0' then
                    data <= din;
                    req  <= '1';
                    bsy  <= '1';
                end if;
            elsif req = '1' and ack_s(1) = '1' then
                req <= '0';
            elsif req = '0' and ack_s(1) = '0' then
                bsy <= '0';
            end if;
        end if;
    end process;

    process (clk_b)
    begin
        if rising_edge(clk_b) then
            req_s  <= req_s(0) & req;
            dvalid_r <= '0';

            if req_s(1) = '1' and ack = '0' then
                dout_r   <= data;
                dvalid_r <= '1';
                ack    <= '1';
            elsif req_s(1) = '0' then
                ack <= '0';
            end if;
        end if;
    end process;
end architecture rtl;
