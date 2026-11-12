# Brief 55: the sandbox image for VHDL designs = fda-sim:2 plus GHDL 4.1.0 (Ubuntu 24.04 package, mcode back end, the version
# used locally and in CI). agent.core.runner.SIM_IMAGE_VHDL; SystemVerilog runs keep fda-sim:2 unchanged.
# Build (after fda-sim:2): docker build -t fda-sim:2-ghdl -f agent/container/Dockerfile.vhdl agent/container   (about 1 minute)
FROM fda-sim:2
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ghdl=4.1.0+dfsg-0ubuntu2.1 ghdl-mcode=4.1.0+dfsg-0ubuntu2.1 ghdl-common=4.1.0+dfsg-0ubuntu2.1 \
    && rm -rf /var/lib/apt/lists/* \
    && ghdl --version | head -1
