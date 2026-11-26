"""Load a dev task's golden model (benchmark/tasks/<task>/hidden/model.py) by path: every task's module is called model."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_model(task: str):
    p = ROOT / "benchmark" / "tasks" / task / "hidden" / "model.py"
    spec = importlib.util.spec_from_file_location(f"model_{task}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
