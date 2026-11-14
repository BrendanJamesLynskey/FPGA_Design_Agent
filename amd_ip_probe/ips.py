"""The AMD IP configurations the probe benches run against (brief 69). One entry per bench: the catalogue name, the
configuration set before generation, and the testbench. run_probe.py reads this; nothing else does."""
IPS = {
    "gpio": {
        "ip": "axi_gpio", "module": "dut_gpio", "tb": "tb_gpio",
        "cfg": {"CONFIG.C_GPIO_WIDTH": 8, "CONFIG.C_IS_DUAL": 1, "CONFIG.C_GPIO2_WIDTH": 4,
                "CONFIG.C_INTERRUPT_PRESENT": 1, "CONFIG.C_DOUT_DEFAULT": "0x000000A5",
                "CONFIG.C_TRI_DEFAULT": "0x000000F0", "CONFIG.C_DOUT_DEFAULT_2": "0x00000005",
                "CONFIG.C_TRI_DEFAULT_2": "0x0000000F"},
    },
    "uartlite": {
        "ip": "axi_uartlite", "module": "dut_uart", "tb": "tb_uartlite",
        "cfg": {"CONFIG.C_BAUDRATE": 230400, "CONFIG.C_DATA_BITS": 8, "CONFIG.C_USE_PARITY": 0},
    },
    "timer": {
        "ip": "axi_timer", "module": "dut_timer", "tb": "tb_timer",
        "cfg": {"CONFIG.mode_64bit": 0, "CONFIG.TRIG0_ASSERT": "Active_High", "CONFIG.GEN0_ASSERT": "Active_High"},
    },
    "intc": {
        "ip": "axi_intc", "module": "dut_intc", "tb": "tb_intc",
        "cfg": {"CONFIG.C_NUM_INTR_INPUTS": 4, "CONFIG.C_KIND_OF_INTR": "0x00000003",
                "CONFIG.C_KIND_OF_EDGE": "0xFFFFFFFF", "CONFIG.C_KIND_OF_LVL": "0xFFFFFFFF"},
    },
    "iic": {
        "ip": "axi_iic", "module": "dut_iic", "tb": "tb_iic",
        "cfg": {"CONFIG.AXI_ACLK_FREQ_MHZ": 100},
    },
    "qspi": {
        "ip": "axi_quad_spi", "module": "dut_qspi", "tb": "tb_qspi",
        "cfg": {"CONFIG.C_SPI_MODE": 0, "CONFIG.FIFO_INCLUDED": 1, "CONFIG.C_FIFO_DEPTH": 16, "CONFIG.Async_Clk": 0},
    },
    "dma": {
        "ip": "axi_dma", "module": "dut_dma", "tb": "tb_dma",
        "cfg": {"CONFIG.c_include_sg": 0},
    },
    "smartconnect": {
        "ip": "smartconnect", "bd": True, "module": "bd_wrapper", "tb": "tb_ic", "cfg": {},
    },
    "axi_interconnect": {
        "ip": "axi_interconnect", "bd": True, "module": "bd_wrapper", "tb": "tb_ic", "cfg": {},
    },
}
