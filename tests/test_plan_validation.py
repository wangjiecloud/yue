import copy

import pytest
from pydantic import ValidationError

from yue_backend.demo import build_ten_making_plan
from yue_backend.models import (
    ChoiceAnswer,
    NumericAnswer,
    Option,
    PracticeItem,
    Question,
)
from yue_backend.validation import validate_plan


def test_demo_plan_passes_validation():
    result = validate_plan(build_ten_making_plan())
    assert result.ok
    assert result.errors == []


def test_false_equation_is_rejected():
    plan = build_ten_making_plan()
    plan.solution.steps[0].expression = "8 + 2 = 11"
    result = validate_plan(plan)
    assert not result.ok
    assert any("false equation" in error for error in result.errors)


def test_final_answer_must_match_arithmetic():
    plan = build_ten_making_plan()
    plan.solution.finalAnswer = "8 + 5 = 12"
    result = validate_plan(plan)
    assert not result.ok


def test_unknown_narration_reference_is_rejected():
    plan = build_ten_making_plan()
    plan.scenes[0].narrationId = "missing"
    result = validate_plan(plan)
    assert any("references unknown narration" in error for error in result.errors)


def test_uncertainties_block_generation():
    plan = build_ten_making_plan()
    plan.question.uncertainties = ["图中第二个数字无法确认"]
    result = validate_plan(plan)
    assert any("uncertainties" in error for error in result.errors)


def test_choice_answer_must_reference_options():
    with pytest.raises(ValidationError):
        Question(
            questionId="q1",
            questionRevision=1,
            grade=1,
            subject="math",
            knowledgePoints=["k"],
            questionType="singleChoice",
            stem="1 + 1 = ?",
            options=[Option(id="a", label="1")],
            answer=ChoiceAnswer(kind="choice", optionId="z"),
        )


def test_practice_kind_must_match_answer_kind():
    with pytest.raises(ValidationError):
        PracticeItem(
            practiceId="p1",
            kind="ordering",
            prompt="排序",
            options=[Option(id="a", label="一")],
            answer=NumericAnswer(kind="numeric", value=1),
            hints=["提示"],
            explanation="解释",
        )


def test_plan_rejects_extra_fields():
    data = build_ten_making_plan().model_dump(mode="json")
    data["surprise"] = True
    with pytest.raises(ValidationError):
        type(build_ten_making_plan()).model_validate(data)


def test_mutating_plan_keeps_original_untouched():
    plan = build_ten_making_plan()
    data = plan.model_dump(mode="json")
    copy.deepcopy(data)["planId"] = "changed"
    assert plan.planId == "plan-demo-8-plus-5"
