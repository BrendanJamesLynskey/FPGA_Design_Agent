"""Integer expressions over a contract's parameters (``"DATA_W * 3"``, ``"H_TOTAL + 2"``), evaluated without ``eval``.

Allowed: integers, parameter names, ``+ - * // % **``, unary minus and parentheses. Anything else is an error, so a
contract can never run code.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}


class ExprError(ValueError):
    pass


def names(expr: Any) -> set[str]:
    """The parameter names an expression uses (empty for a plain integer)."""
    if isinstance(expr, bool):
        return set()
    if isinstance(expr, int):
        return set()
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"{expr!r} is not an integer expression ({e.msg})") from None
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def evaluate(expr: Any, params: dict[str, int]) -> int:
    """The value of ``expr`` with ``params``; :class:`ExprError` for an unknown name or a form that is not allowed."""
    if isinstance(expr, bool):
        raise ExprError(f"{expr!r} is a boolean, not an integer expression")
    if isinstance(expr, int):
        return expr
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"{expr!r} is not an integer expression ({e.msg})") from None

    def ev(n: ast.AST) -> int:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in params:
                raise ExprError(f"{expr!r}: {n.id} is not a declared parameter")
            return int(params[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (b < 0 or b > 64):
                raise ExprError(f"{expr!r}: exponent out of range")
            if isinstance(n.op, (ast.FloorDiv, ast.Mod)) and b == 0:
                raise ExprError(f"{expr!r}: division by zero")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ExprError(f"{expr!r}: only integers, parameter names, + - * // % ** and parentheses are allowed")

    return ev(tree)
