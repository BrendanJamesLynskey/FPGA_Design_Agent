# Sandbox image for agent-written test code (cocotb benches, hw_checks.py): run by agent.core.runner.ContainerRunner
# with no network, no capabilities, read-only root, the host uid. Icarus 12.0 matches the local and CI simulator
# (Icarus 13 rejects an implicit cast in shell/rtl/uart_rx.sv that 12 accepts).
FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv libpython3.12 iverilog make g++ \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
        cocotb==2.0.1 cocotb-coverage==2.0 pytest==9.2.0 PyYAML==6.0.3 find_libpython==0.5.1
ENV PATH=/opt/venv/bin:$PATH
