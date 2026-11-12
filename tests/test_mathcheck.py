from fractions import Fraction

import pytest

from yue_backend.mathcheck import (
    MathCheckError,
    evaluate,
    extract_equations,
    make_fact,
    verify_equation,
    verify_fact,
)
from yue_backend.models import ArithmeticFact


def test_evaluate_basic_operations():
    assert evaluate("8 + 5") == Fraction(13)
    assert evaluate("13 - 5") == Fraction(8)
    assert evaluate("4 * 3") == Fraction(12)
    assert evaluate("10 / 4") == Fraction(5, 2)


def test_evaluate_accepts_unicode_operators():
    assert evaluate("8 × 5") == Fraction(40)
    assert evaluate("10 ÷ 2") == Fraction(5)


def test_evaluate_rejects_dangerous_input():
    for expression in ["__import__('os')", "8 + abc", "8;9", "8 // 2", "pow(2,3)", ""]:
        with pytest.raises(MathCheckError):
            evaluate(expression)


def test_verify_equation_true_and_false():
    lhs, rhs = verify_equation("8 + 2 = 10")
    assert lhs == rhs == Fraction(10)
    with pytest.raises(MathCheckError):
        verify_equation("8 + 2 = 11")
    with pytest.raises(MathCheckError):
        verify_equation("8 + 2")


def test_extract_equations_from_teaching_text():
    text = "先把 8 + 2 = 10，再算 10 + 3 = 13，最后 8 + 5 = 13。"
    equations = extract_equations(text)
    assert equations == ["8 + 2 = 10", "10 + 3 = 13", "8 + 5 = 13"]
    for equation in equations:
        verify_equation(equation)


def test_verify_fact_and_make_fact():
    verify_fact(ArithmeticFact(a=8, op="+", b=5, result=13))
    with pytest.raises(MathCheckError):
        verify_fact(ArithmeticFact(a=8, op="+", b=5, result=12))
    fact = make_fact(7, "+", 6)
    assert fact.result == 13
    with pytest.raises(MathCheckError):
        make_fact(7, "/", 0)
