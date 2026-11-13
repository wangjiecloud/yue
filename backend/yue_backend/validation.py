from __future__ import annotations

from dataclasses import dataclass, field

from .mathcheck import verify_question_math, verify_solution_math
from .models import Course, Manifest, TeachingPlan


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.errors:
            raise PlanValidationError(self)


class PlanValidationError(ValueError):
    def __init__(self, result: ValidationResult):
        self.result = result
        super().__init__("; ".join(result.errors))


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicated: set[str] = set()
    for value in values:
        if value in seen:
            duplicated.add(value)
        seen.add(value)
    return sorted(duplicated)


def validate_plan(plan: TeachingPlan) -> ValidationResult:
    result = ValidationResult()

    narration_ids = [segment.id for segment in plan.narrations]
    scene_ids = [scene.sceneId for scene in plan.scenes]
    chapter_ids = [chapter.chapterId for chapter in plan.chapters]

    for label, values in (
        ("narration id", narration_ids),
        ("scene id", scene_ids),
        ("chapter id", chapter_ids),
    ):
        for duplicated in _duplicates(values):
            result.errors.append(f"duplicate {label}: {duplicated}")

    narration_set = set(narration_ids)
    scene_set = set(scene_ids)
    chapter_set = set(chapter_ids)

    for scene in plan.scenes:
        if scene.narrationId not in narration_set:
            result.errors.append(f"scene {scene.sceneId} references unknown narration")
        if scene.chapterId not in chapter_set:
            result.errors.append(f"scene {scene.sceneId} references unknown chapter")

    for chapter in plan.chapters:
        if chapter.sceneId not in scene_set:
            result.errors.append(f"chapter {chapter.chapterId} references unknown scene")
            continue
        scene = next(item for item in plan.scenes if item.sceneId == chapter.sceneId)
        if scene.chapterId != chapter.chapterId:
            result.errors.append(
                f"chapter {chapter.chapterId} and scene {scene.sceneId} disagree on chapter"
            )

    result.errors.extend(verify_question_math(plan.question))
    result.errors.extend(verify_solution_math(plan.question, plan.solution))

    if plan.question.uncertainties:
        result.errors.append(
            "question has unresolved uncertainties: " + ", ".join(plan.question.uncertainties)
        )

    for scene in plan.scenes:
        if scene.template == "tenFrame" and scene.operands:
            a, b = scene.operands
            facts = {(fact.a, fact.op, fact.b) for fact in plan.question.arithmetic}
            if plan.question.subject == "math" and (a, "+", b) not in facts:
                result.warnings.append(
                    f"tenFrame scene {scene.sceneId} operands {a}+{b} are not in question arithmetic"
                )

    for practice in plan.practice:
        if not practice.hints:
            result.errors.append(f"practice {practice.practiceId} has no hint")
        if practice.kind == "pairing":
            if not practice.left or not practice.right:
                result.errors.append(
                    f"practice {practice.practiceId} must define left and right pair sides"
                )
            if practice.answer.kind == "pairing" and practice.left and practice.right:
                left_ids = {side.id for side in practice.left}
                right_ids = {side.id for side in practice.right}
                for pair in practice.answer.pairs:
                    if pair.leftId not in left_ids or pair.rightId not in right_ids:
                        result.errors.append(
                            f"practice {practice.practiceId} pairs an unknown side"
                        )
        elif practice.kind in {"ordering", "dragDrop", "singleChoice"} and not practice.options:
            result.errors.append(f"practice {practice.practiceId} has no options")

    if not plan.practice:
        result.warnings.append("plan has no practice item; only lectureOnly courses are allowed")

    if not any(scene.template == "closing" for scene in plan.scenes):
        result.warnings.append("plan has no closing scene")

    if not plan.diagnosis.visibleError and not plan.diagnosis.commonMisconceptions:
        result.warnings.append("plan has no visible error or common misconception notes")

    return result


def validate_course(course: Course, manifest: Manifest | None = None) -> ValidationResult:
    result = ValidationResult()
    lesson_ids = [lesson.lessonId for lesson in course.lessons]
    for duplicated in _duplicates(lesson_ids):
        result.errors.append(f"duplicate lesson id: {duplicated}")

    practice_ids = [practice.practiceId for practice in course.practices]
    for duplicated in _duplicates(practice_ids):
        result.errors.append(f"duplicate practice id: {duplicated}")
    practice_set = set(practice_ids)
    asset_ids = {asset.assetId for asset in manifest.assets} if manifest else set()

    for lesson in course.lessons:
        steps = {step.id: step for step in lesson.steps}
        if len(steps) != len(lesson.steps):
            result.errors.append(f"lesson {lesson.lessonId} has duplicate step ids")
        if lesson.entryStepId not in steps:
            result.errors.append(f"lesson {lesson.lessonId} has unknown entry step")
            continue
        if lesson.entryStepId != "tutorial":
            result.warnings.append(f"lesson {lesson.lessonId} does not start with the video step")

        for step in lesson.steps:
            for target in (
                step.nextStepId,
                step.onCorrect,
                step.onIncorrect,
                step.onAttemptsExhausted,
            ):
                if target and target not in steps:
                    result.errors.append(f"step {step.id} references unknown step {target}")
            if step.type == "interaction":
                practice_id = (step.interaction or {}).get("practiceId")
                if practice_id not in practice_set:
                    result.errors.append(
                        f"step {step.id} references unknown practice {practice_id!r}"
                    )
                if not step.onCorrect or not step.onIncorrect:
                    result.errors.append(
                        f"interaction step {step.id} must define correct and incorrect branches"
                    )
                if step.type == "interaction" and step.maxAttempts and not step.onAttemptsExhausted:
                    result.errors.append(
                        f"interaction step {step.id} must define an exhausted branch"
                    )
            if step.assetId and asset_ids and step.assetId not in asset_ids:
                result.errors.append(f"step {step.id} references unknown asset {step.assetId}")

        reachable: set[str] = set()
        stack = [lesson.entryStepId]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            step = steps.get(current)
            if step is None:
                continue
            for target in (
                step.nextStepId,
                step.onCorrect,
                step.onIncorrect,
                step.onAttemptsExhausted,
            ):
                if target:
                    stack.append(target)
        unreachable = sorted(set(steps) - reachable)
        if unreachable:
            result.errors.append(
                f"lesson {lesson.lessonId} has unreachable steps: {', '.join(unreachable)}"
            )
        for step in lesson.steps:
            if step.type not in {"finish", "feedback", "interaction"} and not step.nextStepId:
                result.errors.append(f"step {step.id} is a dead end without nextStepId")

        if lesson.courseMode == "interactive" and not lesson.practiceIds:
            result.errors.append(f"interactive lesson {lesson.lessonId} has no practice")
        if lesson.courseMode == "lectureOnly" and lesson.practiceIds:
            result.errors.append(f"lectureOnly lesson {lesson.lessonId} must not declare practice")

        if lesson.chapters:
            starts = [chapter.startMs for chapter in lesson.chapters]
            if starts != sorted(starts):
                result.errors.append(f"lesson {lesson.lessonId} chapters are not ordered")
            if lesson.durationMs and starts and starts[-1] >= lesson.durationMs:
                result.errors.append(
                    f"lesson {lesson.lessonId} chapter starts beyond video duration"
                )

    if manifest is not None:
        if manifest.courseId != course.courseId or manifest.revision != course.revision:
            result.errors.append("manifest and course identity do not match")
        if manifest.courseMode != course.lessons[0].courseMode:
            result.errors.append("manifest and lesson courseMode do not match")

    return result
