"""Run `python -m agent run ...` with the stage-1 tool list as built (arm `with`) or with ip_lookup removed from it (arm `without`).

    PYTHONPATH=. python results/150_ip_lookup/stage1_trial/run_arm.py with|without run <spec.md> --name N --interview off --stop-after 1 ...
"""
import sys

arm, args = sys.argv[1], sys.argv[2:]
from agent.graph import stages

if arm == "without":
    st = stages.MACHINE[1]
    object.__setattr__(st, "tools", tuple(t for t in st.tools if t != "ip_lookup"))   # the stage-1 bullet is guarded by the same test
from agent.__main__ import main

sys.exit(main(args))
