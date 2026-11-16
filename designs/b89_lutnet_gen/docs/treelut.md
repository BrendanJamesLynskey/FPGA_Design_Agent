# TreeLUT as the reference point

TreeLUT (Alireza Khataei and Kia Bazargan, "TreeLUT: An Efficient Alternative to Deep Neural Networks for Inference
Acceleration Using Gradient Boosted Decision Trees", FPGA '25, arXiv 2501.01511) is the published tool that turns
boosted trees into LUT logic. Here it is the yardstick for our generator, not part of it.

## Approval and pinning

- **Approval.** The owner approved the install on 2026-11-15: house rules, "Third-party tool approval: TreeLUT".
- **Source.** https://github.com/kiabuzz/TreeLUT, MIT licence, pinned at commit
  `ad9e70a9ba1a74ccf8df97a3f7fcdc9137e68b21`.
- **Checked before installing.** `setup.py` is a plain setuptools call with `install_requires=['numpy',
  'xgboost>=2.1.1']`. It has no install hooks, and there is no `pyproject.toml` or `setup.cfg`.
- **Environment.** The tool sits in its own venv, `~/Claude_sandbox/_worktrees/89-treelut/venv`, installed with
  `pip install --no-deps ./src`. Its dependencies were installed separately:
  - numpy 2.4.3;
  - `xgboost-cpu` 3.1.3, the CPU-only wheel, which avoids the CUDA dependency of `xgboost`;
  - scikit-learn 1.9.1.

  The exact list is in `_worktrees/89-treelut/pip_freeze.txt`.
- **What is committed.** Only the Verilog TreeLUT generated (`rtl/treelut/*.v`, with `NOTICE.md`) and our
  measurements. `treelut_arm.sv`, the wrapper with the 87 arm ports, is our code.

## How it was run (`treelut_ref/run_treelut.py`)

- Features go in unchanged with `w_feature = 8`, because every 87 feature is an unsigned integer of at most 8 bits.
- XGBoost `multi:softmax`, `subsample = 0.8`, `tree_method = exact`.
- Validation grid: trees 10, 20 or 40 per class; depth 2, 3 or 4; `eta = 0.3`; `w_tree` 2, 3 or 4. The rule is the
  best validation accuracy of the TreeLUT-quantised model, then the smallest model within 0.002 of it. The chosen
  point is 20 trees x depth 4 with `w_tree = 4`, val 0.4876 (`results/b89/treelut/tuning.json`).
- TreeLUT pipeline `[0, 1, 1]`: one register after the trees and one inside the adders. Our wrapper adds the argmax
  and the output register, giving LATENCY 3.

## Known limits of the comparison

- The grid fixes `eta`, caps depth at 4, and does not quantise the inputs below 8 bits. The point is tuned for
  accuracy, not cost, so a leaner TreeLUT point could use fewer LUTs.
- Only seed 0 is built. Seed 0 is not selected on validation, while our built seed is.
- `XGBClassifier.load_model` does not restore `n_estimators`, which TreeLUT reads. `run_treelut.load` sets it again.
