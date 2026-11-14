#include "acc_bench.h"
void app_main(void) {
    rt_init(1); g_uart_on = 0;
    ops_banner("crc32_offload"); xadc_alarms_setup();
    static const uint32_t sizes[] = {16, 64, 256, 1024, 4096, 8192, 16384, 32768, 65536, 262144, 1048576};
    run_sizes(0, sizes, sizeof sizes / sizeof sizes[0]);
    xadc_report("end"); uart_puts("DONE\n");
}
