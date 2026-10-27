"""Safe arithmetic: a whitelist AST evaluator, never `eval` (PRD §9.4)."""

import ast
import operator as op
from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool

MAX_LEN = 200
MAX_EXPONENT = 12
_BIN: dict[type, Callable[..., Any]] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
}
_UNARY: dict[type, Callable[..., Any]] = {ast.UAdd: op.pos, ast.USub: op.neg}
_FUNCS: dict[str, Callable[..., Any]] = {"abs": abs, "round": round, "min": min, "max": max}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError(f"exponent larger than {MAX_EXPONENT} is not allowed")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError(f"not allowed in a calculation: {type(node).__name__}")


def calculate(expression: str) -> float:
    """Evaluate +, -, *, /, **, %, parentheses and abs/round/min/max over plain numbers. Raises ValueError otherwise."""
    expression = expression.replace(",", "").strip()
    if not expression or len(expression) > MAX_LEN:
        raise ValueError(f"expression must be 1 to {MAX_LEN} characters")
    try:
        return float(_eval(ast.parse(expression, mode="eval").body))
    except ZeroDivisionError as e:
        raise ValueError("division by zero") from e
    except SyntaxError as e:
        raise ValueError("not a valid arithmetic expression") from e


@tool("calculator")
def calculator_tool(expression: str) -> str:
    """Evaluate an arithmetic expression such as '(69900 - 127000) / 127000 * 100'. Use it for any arithmetic on
    numbers you already have; prefer compute_change when the numbers come from query_statistic. Plain numbers
    only: no variables or text."""
    try:
        return f"{expression} = {calculate(expression):.6g}"
    except ValueError as e:
        return f"Error: {e}"
