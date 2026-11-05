# Sandbox image for agent-written test code (cocotb benches, hw_checks.py): run by agent.core.runner.ContainerRunner
# with no network, no capabilities, read-only root, the host uid. Icarus 12.0 matches the local and CI simulator
# (Icarus 13 rejects an implicit cast in shell/rtl/uart_rx.sv that 12 accepts). fda-sim:2 adds Verilator 5.048 (the
# version of the host install; Ubuntu 24.04's apt Verilator 5.020 is too old for cocotb 2, which needs 5.036+),
# built from source in a first stage so the compilers and sources of the build are not in the final image.
# Rebuild: docker build -t fda-sim:2 agent/container   (about 10 minutes; cap it: see docs/agent_core.md)
FROM ubuntu:24.04 AS verilator-build
ARG VERILATOR_TAG=v5.048
ARG JOBS=2
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git ca-certificates autoconf automake libtool flex bison help2man perl python3 make g++ \
        libfl2 libfl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${VERILATOR_TAG} https://github.com/verilator/verilator /src/verilator \
    && cd /src/verilator && autoconf \
    && ./configure --prefix=/opt/verilator \
    && make -j${JOBS} && make install \
    && /opt/verilator/bin/verilator --version | grep -q "Verilator ${VERILATOR_TAG#v} "

FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv libpython3.12 iverilog make g++ perl libfl2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=verilator-build /opt/verilator /opt/verilator
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
        cocotb==2.0.1 cocotb-coverage==2.0 pytest==9.2.0 PyYAML==6.0.3 find_libpython==0.5.1
ENV PATH=/opt/verilator/bin:/opt/venv/bin:$PATH
RUN verilator --version && iverilog -V | head -1
