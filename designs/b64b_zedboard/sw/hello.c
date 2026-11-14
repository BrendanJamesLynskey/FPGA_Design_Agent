#include "rt.h"
void app_main(void) {
    rt_init(0);
    uart_puts("HELLO ZedBoard bump: Cortex-A9 core 0 bare metal, UART1 115200 8N1\n");
    uart_puts("MIDR "); uint32_t m; __asm__ volatile("mrc p15,0,%0,c0,c0,0" : "=r"(m)); uart_hex(m); uart_puts("\n");
    uart_puts("PS_VERSION(0xF8007080) "); uart_hex(REG(0xF8007080)); uart_puts("\n");
    uart_puts("DDR test 0x01000000..: ");
    volatile uint32_t *p = (volatile uint32_t *)0x01000000; int bad = 0;
    for (uint32_t i = 0; i < 262144; i++) p[i] = i * 2654435761u;
    for (uint32_t i = 0; i < 262144; i++) if (p[i] != i * 2654435761u) bad++;
    uart_puts(bad ? "FAIL " : "PASS "); uart_dec(bad); uart_puts(" mismatches in 1 MB\n");
    xadc_init();
    uart_puts("XADC raw temp/vccint/vccaux/vccbram: ");
    uart_hex(xadc_read(0)); uart_putc(' '); uart_hex(xadc_read(1)); uart_putc(' '); uart_hex(xadc_read(2)); uart_putc(' '); uart_hex(xadc_read(6)); uart_puts("\n");
    uart_puts("LED reg (GPIO @0x40000000) write 0xA5, read back: ");
    REG(PL_BASE) = 0xA5; uart_hex(REG(PL_BASE)); uart_puts("\nDONE\n");
}
