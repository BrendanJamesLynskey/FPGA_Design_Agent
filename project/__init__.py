"""The project layer (brief 27 Part B, stage P0): a design made of several modules, above the single-design run.

A project is a directory (a git repository) with a ``design.yaml`` (the module graph, the clock and reset plan, the
board ports) and, per module, ``modules/<m>/contract.yaml`` (the interface contract). See ``docs/design_environment.md``
for the design and ``docs/project_layer.md`` for the file formats. This package is separate from ``agent/``: it adds no
registered tool and changes no request path (``agent/tests/test_08f_golden_requests.py``).

- :mod:`project.schema`: the checkers for ``design.yaml``, ``contract.yaml`` and ``system/requirements.yaml``;
- :mod:`project.stages`: the input hash of each (module, stage), chained so an upstream change makes every later stage
  stale;
- :mod:`project.status`: current / stale / missing evidence per module and stage, and the re-entry point;
- :mod:`project.dashboard`: a static, self-contained HTML page of the module graph and the status;
- :mod:`project.contract_test`: generates a cocotb contract test from a ``contract.yaml``, mechanically (no model);
  the checks themselves live in :mod:`project.contract_bench`.

    python -m project check  <dir>
    python -m project status <dir> [--json OUT] [--html OUT]
    python -m project hash   <dir> [--module M]
    python -m project gen-tests <dir> [--module M]
"""
