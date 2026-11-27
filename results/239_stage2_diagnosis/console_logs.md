Verilator lint logs: 463 logs (the gate or the Designer's `lint` tool) over 36 runs; 93 clean, 316 with warnings only in the supplied data/ file, 54 with a finding in the design's own files.

| rule | file kind | file | runs | hits |
|---|---|---|---|---|
| UNUSEDSIGNAL | supplied data/ | jtag_bus.sv | 36 | 710 |
| DECLFILENAME | design rtl/ | xilinx_sim_stubs.sv | 13 | 15 |
| PROCASSINIT | design rtl/ | xilinx_sim_stubs.sv | 12 | 40 |
| UNUSEDPARAM | design rtl/ | xilinx_sim_stubs.sv | 10 | 115 |
| UNUSEDSIGNAL | design rtl/ | p2_core.sv | 6 | 8 |
| PROCASSINIT | design rtl/ | por_gen.sv | 4 | 7 |
| PINCONNECTEMPTY | design rtl/ | freq_meter_top.sv | 4 | 6 |
| BADVLTPRAGMA | design rtl/ | lint_waivers.sv | 4 | 4 |
| PINCONNECTEMPTY | design rtl/ | p2_core.sv | 3 | 7 |
| PINCONNECTEMPTY | design rtl/ | freq_meter_core.sv | 3 | 5 |
| SYNCASYNCNET | design rtl/ | freq_meter_top.sv | 3 | 3 |
| PINCONNECTEMPTY | design rtl/ | crc32_top.sv | 3 | 25 |
| PROCASSINIT | design rtl/ | crc32_top.sv | 3 | 6 |
| PROCASSINIT | design rtl/ | freq_meter_core.sv | 3 | 16 |
| PINCONNECTEMPTY | design rtl/ | crc32_core.sv | 3 | 8 |
| PROCASSINIT | design rtl/ | freq_meter_top.sv | 2 | 4 |
| BADVLTPRAGMA | design rtl/ | lint_waive.sv | 2 | 2 |
| PROCASSINIT | design rtl/ | rst_gen.sv | 2 | 4 |
| PINCONNECTEMPTY | design rtl/ | p2_top.sv | 2 | 4 |
| DECLFILENAME | design rtl/ | crc32_top.sv | 2 | 2 |

Design-standards rules that failed in a `standards` log (any call):

| rule | runs | hits |
|---|---|---|
| STD-CDC-01 | 25 | 73 |
| STD-RST-01 | 11 | 11 |
| STD-CLK-01 | 4 | 4 |
| STD-INIT-02 | 1 | 1 |
