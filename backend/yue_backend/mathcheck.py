"""Independent arithmetic verification.

Model output is never trusted for correctness: every arithmetic relation that
the plan claims is re-computed here with a whitelist AST evaluator. No model
text is ever executed.
"""

from __future__ import annotations

import ast
import re
from fractions import Fraction

from .models import ArithmeticFact, Question, Solution

_OPERATOR_MAP = str.maketrans(
    {"×": "*", "x": "*", "X": "*", "÷": "/", "−": "-", "—": "-", "＝": "="}
)
_EQUATION_RE = re.compile(r"[0-9()+\-*/.×÷−＝= ]+=[0-9()+\-*/.×÷−＝= ]+")


class MathCheckError(ValueError):
    pass


def _eval_node(node: ast.AST) -> Fraction:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MathCheckError("only numeric constants are allowed")
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise MathCheckError("division by zero")
            return left / right
        raise MathCheckError("unsupported operator")
    raise MathCheckError("unsupported expression")


def evaluate(expression: str) -> Fraction:
    cleaned = expression.translate(_OPERATOR_MAP).strip()
    if not cleaned or not re.fullmatch(r"[0-9()+\-*/.\s]+", cleaned):
        raise MathCheckError(f"expression contains unsupported characters: {expression!r}")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise MathCheckError(f"invalid expression: {expression!r}") from exc
    return _eval_node(tree)


def verify_equation(expression: str) -> tuple[Fraction, Fraction]:
    """Return (lhs, rhs), raising when the equation is false or malformed."""
    cleaned = expression.translate(_OPERATOR_MAP)
    if cleaned.count("=") != 1:
        raise MathCheckError(f"expected exactly one '=' in {expression!r}")
    lhs_text, rhs_text = cleaned.split("=")
    lhs = evaluate(lhs_text)
    rhs = evaluate(rhs_text)
    if lhs != rhs:
        raise MathCheckError(f"false equation: {expression!r} ({lhs} != {rhs})")
    return lhs, rhs


def extract_equations(text: str) -> list[str]:
    normalized = text.translate(_OPERATOR_MAP)
    matches = _EQUATION_RE.findall(normalized)
    return [match.strip() for match in matches if "=" in match]


def verify_fact(fact: ArithmeticFact) -> None:
    expression = f"{fact.a} {fact.op} {fact.b}"
    value = evaluate(expression)
    if value != Fraction(fact.result):
        raise MathCheckError(
            f"arithmetic fact is false: {fact.a} {fact.op} {fact.b} = {fact.result}"
        )


def verify_question_math(question: Question) -> list[str]:
    errors: list[str] = []
    for fact in question.arithmetic:
        try:
            verify_fact(fact)
        except MathCheckError as exc:
            errors.append(str(exc))
    return errors


def verify_solution_math(question: Question, solution: Solution) -> list[str]:
    errors: list[str] = []
    for step in solution.steps:
        sources = [step.expression] if step.expression else []
        sources.append(step.text)
        for source in sources:
            if not source:
                continue
            for equation in extract_equations(source):
                try:
                    verify_equation(equation)
                except MathCheckError as exc:
                    errors.append(f"step {step.index}: {exc}")
    for equation in extract_equations(solution.finalAnswer):
        try:
            verify_equation(equation)
        except MathCheckError as exc:
            errors.append(f"final answer: {exc}")

    if question.arithmetic:
        primary = question.arithmetic[0]
        expected = evaluate(f"{primary.a} {primary.op} {primary.b}")
        final_numbers = re.findall(r"-?\d+(?:\.\d+)?", solution.finalAnswer)
        if final_numbers and Fraction(final_numbers[-1]) != expected:
            errors.append(
                f"final answer value {final_numbers[-1]} does not match computed {expected}"
            )
    return errors


def make_fact(a: int, op: str, b: int) -> ArithmeticFact:
    result = evaluate(f"{a} {op} {b}")
    if result.denominator != 1:
        raise MathCheckError("integer-only arithmetic facts are required")
    return ArithmeticFact(a=a, op=op, b=b, result=int(result))
