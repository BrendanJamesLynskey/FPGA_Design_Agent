# Build dbg_xvc: the board side (brief 131; written, not run)

**Nothing here has been run on a board.** There are no runnable commands in this page on purpose (owner rule: commands only when it is time). The planner gives each step
at the board from `dbg_xvc/board/xvc_board_session.sh`. Terms: XVC = Xilinx Virtual Cable, a TCP protocol that carries JTAG shifts, so Vivado's hardware manager can use a network
connection where it would use a USB cable; UIO = Linux's user-space I/O framework (a driver that only maps a device's registers into a program); ILA = integrated logic analyser.

## What runs where

| Where | What | Source |
|---|---|---|
| PL (the bitstream of build dbg_xvc) | PS master M_AXI_HPM0_LPD, AXI4 to AXI4-Lite converter, Debug Bridge "From AXI to BSCAN", one ILA | `rtl/xvc_debug.sv`, `ip/amd_ip_xvc.tcl` |
| KR260 Linux (Ubuntu, not PetaLinux) | an XVC server that turns XVC shifts into reads and writes of the bridge's five registers | AMD's open-source XVC server (see below) |
| The PC | Vivado hardware manager, "Add Xilinx Virtual Cable", the build's probes file | Vivado 2026.1 |

## Which XVC variant fits Ubuntu, and why

AMD's repository (Xilinx/XilinxVirtualCable on GitHub, https://github.com/Xilinx/XilinxVirtualCable, folder `jtag/zynqMP`) has two ways for the same server to reach the bridge, per its README files:

1. **ioctl build with a kernel driver** (`src/driver`, device node per bridge, device-tree compatible `xlnx,xvc`). The driver is compiled against the kernel source tree of the running kernel
   (its README names `KERNEL_SRC`); the page does not say whether the installed headers alone are enough. On the KR260's Ubuntu, that means installing the exact `linux-headers` of the booted kernel and
   building a module on the board (or cross-building against matching sources); a kernel upgrade then needs a rebuild. This is the route the article by Adam Taylor takes on PetaLinux
   (https://www.hackster.io/adam-taylor/debugging-hw-ilas-with-petalinux-over-ethernet-be6218), where Yocto builds the module together with the kernel.
2. **mmap build through generic UIO** (`src/user`, `xvcServer_mmap`): the server maps the bridge's registers through the kernel's own generic UIO driver. No module is built and nothing depends on the kernel version,
   if the running kernel carries the generic UIO platform driver (`uio_pdrv_genirq`) and is told to bind it to the device-tree compatible string `generic-uio`.

**Recommendation: variant 2, the user-space mmap build**, because it needs no kernel headers and survives Ubuntu kernel updates. **Unconfirmed** (nothing run): that the KR260's Ubuntu kernel has `uio_pdrv_genirq` available (built in or as a
module) and accepts the `of_id=generic-uio` binding on its command line or as a module option; that the server's source defaults to TCP port 2542 (the conventional XVC port: the server's own source decides, and the session script assumes 2542).
**Fallback if UIO is unavailable:** variant 1 (build against the board's exact kernel headers) or, with no module at all, the same server reading `/dev/mem` (a source change to the server, with the cost that `/dev/mem` may be
restricted by the kernel configuration). The first board minute therefore checks one thing: that the UIO device node appears for the bridge after the overlay loads.

## Loading the PL through Linux (the overlay route)

The KR260 loads PL images from Linux through the Kria `xmutil` tool as an "app": a directory with the bitstream in `.bit.bin` form, the overlay `.dtbo` and `shell.json`.
`dbg_xvc/board/pl-dbg-xvc.dtsi` is the overlay source (compiled with `dtc`), `dbg_xvc/board/shell.json` the app descriptor. The `.bit.bin` is made from the build's `.bit` with AMD's `bootgen` (a one-line BIF naming the bitstream).
Why through Linux and not the JTAG cable: the whole point is that no JTAG traffic is needed while Linux runs, and a PS master is only usable when Linux's fpga-manager has loaded the PL with the PS-PL interface enabled.
Overlay content: the `fpga_full` fragment names the firmware file; the `amba` fragment adds a node `debug_bridge@80000000`, compatible `generic-uio`, 64 KiB at 0x80000000 (the LPD master window). **Unconfirmed**: the
address (from the address map in AMD's UG1085, to be checked against Vivado's address editor before the first load) and that the Kria base overlay offers the `fpga_full` and `amba` labels under these names (they are in the stock Kria app overlays; the
board's own `.dtbo` files are the reference).

## Connecting Vivado

In the hardware manager: open a new hardware target, choose "Add Xilinx Virtual Cable", enter the board's address and port, then point the device at the build's probes file (`.ltx`, written next to the bitstream). The ILA then appears as on a USB cable.
The scripted version is `dbg_xvc/board/xvc_capture.tcl`. It never opens the USB cable's hardware server target.

## Safety of the network path

XVC has no authentication. The server is started only for the test, bound to the direct link between the PC and the board, and stopped at the end (the script stops only what it started). The bridge reaches the ILA's debug hub only: there is no path from it to
configuration memory, flash, eFUSE or the design's registers (docs/dbg_xvc.md, "What the path can and cannot reach").
