from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Grade = Literal[1, 2, 3]
Subject = Literal["math", "chinese", "english"]
Language = Literal["zh", "en"]
Emotion = Literal["neutral", "encourage", "think", "celebrate", "explain"]
CourseMode = Literal["interactive", "lectureOnly"]


class Option(StrictModel):
    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=200)


class ArithmeticFact(StrictModel):
    """A machine-checkable arithmetic relation extracted from the question."""

    a: int
    op: Literal["+", "-", "*", "/"]
    b: int
    result: int


class NumericAnswer(StrictModel):
    kind: Literal["numeric"] = "numeric"
    value: int | float


class ChoiceAnswer(StrictModel):
    kind: Literal["choice"] = "choice"
    optionId: str


class PairStrict(StrictModel):
    leftId: str
    rightId: str


class PairingAnswer(StrictModel):
    kind: Literal["pairing"] = "pairing"
    pairs: list[PairStrict] = Field(min_length=1)


class OrderingAnswer(StrictModel):
    kind: Literal["ordering"] = "ordering"
    order: list[str] = Field(min_length=1)


AnswerRule = Annotated[
    NumericAnswer | ChoiceAnswer | PairingAnswer | OrderingAnswer,
    Field(discriminator="kind"),
]


class Question(StrictModel):
    questionId: str = Field(min_length=1, max_length=128)
    questionRevision: int = Field(ge=1)
    grade: Grade
    subject: Subject
    knowledgePoints: list[str] = Field(min_length=1)
    questionType: Literal[
        "singleChoice",
        "counting",
        "comparison",
        "pairing",
        "ordering",
        "wordProblem",
        "listening",
        "reading",
        "openEnded",
    ]
    stem: str = Field(min_length=1, max_length=500)
    options: list[Option] = Field(default_factory=list)
    answer: AnswerRule
    arithmetic: list[ArithmeticFact] = Field(default_factory=list)
    visibleWork: str | None = Field(default=None, max_length=500)
    uncertainties: list[str] = Field(default_factory=list)
    isWithinScope: bool = True

    @model_validator(mode="after")
    def _check_choice(self) -> Question:
        if isinstance(self.answer, ChoiceAnswer):
            ids = {option.id for option in self.options}
            if self.answer.optionId not in ids:
                raise ValueError("answer.optionId must reference a declared option")
        if isinstance(self.answer, PairingAnswer):
            ids = {option.id for option in self.options}
            for pair in self.answer.pairs:
                if pair.leftId not in ids or pair.rightId not in ids:
                    raise ValueError("pairing answer references an unknown option")
        if isinstance(self.answer, OrderingAnswer):
            ids = {option.id for option in self.options}
            if not set(self.answer.order).issubset(ids):
                raise ValueError("ordering answer references an unknown option")
        return self


class SolutionStep(StrictModel):
    index: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=400)
    expression: str | None = Field(default=None, max_length=120)


class Solution(StrictModel):
    steps: list[SolutionStep] = Field(min_length=1)
    finalAnswer: str = Field(min_length=1, max_length=120)
    method: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def _sequential(self) -> Solution:
        indices = [step.index for step in self.steps]
        if indices != list(range(1, len(indices) + 1)):
            raise ValueError("solution steps must be numbered sequentially from 1")
        return self


class Diagnosis(StrictModel):
    visibleError: str | None = Field(default=None, max_length=500)
    commonMisconceptions: list[str] = Field(default_factory=list, max_length=5)


class NarrationSegment(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=600)
    language: Language
    emotion: Emotion = "neutral"


class Scene(StrictModel):
    sceneId: str = Field(min_length=1, max_length=64)
    template: Literal[
        "title",
        "questionBoard",
        "tenFrame",
        "summaryBoard",
        "closing",
        "wordPairBoard",
        "pinyinBoard",
    ]
    narrationId: str
    chapterId: str
    title: str | None = Field(default=None, max_length=120)
    subtitle: str | None = Field(default=None, max_length=300)
    text: str | None = Field(default=None, max_length=400)
    operands: list[int] | None = None
    expressions: list[str] = Field(default_factory=list, max_length=8)
    emphasis: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _template_requirements(self) -> Scene:
        if self.template == "tenFrame":
            if not self.operands or len(self.operands) != 2:
                raise ValueError("tenFrame requires exactly two operands")
            if any(value < 0 or value > 10 for value in self.operands):
                raise ValueError("tenFrame operands must be between 0 and 10")
            if sum(self.operands) > 20:
                raise ValueError("tenFrame operands must sum to at most 20")
        if self.template == "questionBoard" and not self.text:
            raise ValueError("questionBoard requires text")
        if self.template == "summaryBoard" and not self.text and not self.expressions:
            raise ValueError("summaryBoard requires text or expressions")
        return self


class Chapter(StrictModel):
    chapterId: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    sceneId: str


class PracticeItem(StrictModel):
    practiceId: str = Field(min_length=1, max_length=64)
    kind: Literal["singleChoice", "pairing", "ordering", "dragDrop"]
    prompt: str = Field(min_length=1, max_length=400)
    options: list[Option] = Field(default_factory=list)
    answer: AnswerRule
    hints: list[str] = Field(min_length=1, max_length=3)
    explanation: str = Field(min_length=1, max_length=500)
    knowledgePoints: list[str] = Field(default_factory=list)
    maxAttempts: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def _kind_matches_answer(self) -> PracticeItem:
        expected = {
            "singleChoice": {"choice"},
            "dragDrop": {"choice", "numeric"},
            "pairing": {"pairing"},
            "ordering": {"ordering"},
        }[self.kind]
        if self.answer.kind not in expected:
            raise ValueError(f"{self.kind} practice cannot use {self.answer.kind} answer")
        if self.answer.kind == "choice" and self.answer.optionId not in {
            option.id for option in self.options
        }:
            raise ValueError("practice answer references an unknown option")
        return self


class PlanMeta(StrictModel):
    generator: str = "yue"
    model: str = ""
    promptVersion: str = "p1-v1"
    toolVersion: str = "0.1.0"
    placeholderAudio: bool = False
    createdAt: str = ""


class TeachingPlan(StrictModel):
    """Internal computer-side plan. The App never executes this directly."""

    schemaVersion: Literal[1] = 1
    planId: str = Field(min_length=1, max_length=128)
    question: Question
    solution: Solution
    diagnosis: Diagnosis
    narrations: list[NarrationSegment] = Field(min_length=1)
    scenes: list[Scene] = Field(min_length=1)
    chapters: list[Chapter] = Field(min_length=1)
    practice: list[PracticeItem] = Field(default_factory=list, max_length=2)
    meta: PlanMeta = Field(default_factory=PlanMeta)


# --- Course package runtime protocol (App side) ---


class ChapterTime(StrictModel):
    chapterId: str
    title: str
    startMs: int = Field(ge=0)


class LessonStep(StrictModel):
    id: str
    type: Literal[
        "display",
        "narrate",
        "video",
        "character",
        "animateObjects",
        "interaction",
        "feedback",
        "reward",
        "finish",
    ]
    assetId: str | None = None
    prompt: str | None = None
    text: str | None = None
    result: Literal["correct", "incorrect", "assisted"] | None = None
    interaction: dict | None = None
    nextStepId: str | None = None
    onCorrect: str | None = None
    onIncorrect: str | None = None
    maxAttempts: int | None = Field(default=None, ge=1, le=3)
    onAttemptsExhausted: str | None = None
    rewardKey: str | None = None
    amount: int | None = None


class Lesson(StrictModel):
    lessonId: str
    questionId: str
    questionRevision: int = Field(ge=1)
    title: str
    courseMode: CourseMode
    videoAssetId: str
    durationMs: int = Field(ge=0)
    subtitleAssetId: str | None = None
    chapters: list[ChapterTime] = Field(default_factory=list)
    entryStepId: str
    steps: list[LessonStep] = Field(min_length=1)
    practiceIds: list[str] = Field(default_factory=list)


class Course(StrictModel):
    schemaVersion: Literal[1] = 1
    courseId: str
    revision: int = Field(ge=1)
    grade: Grade
    subject: Subject
    knowledgePoints: list[str] = Field(default_factory=list)
    lessons: list[Lesson] = Field(min_length=1)
    practices: list[PracticeItem] = Field(default_factory=list)


class ManifestAsset(StrictModel):
    assetId: str
    path: str
    kind: Literal["video", "audio", "image", "subtitle", "animation"]
    sha256: str
    bytes: int = Field(ge=0)
    durationMs: int | None = None


class Manifest(StrictModel):
    packageId: str
    courseId: str
    revision: int = Field(ge=1)
    schemaVersion: Literal[1] = 1
    minimumAppVersion: str = "0.1.0"
    courseMode: CourseMode
    requiredCapabilities: list[str] = Field(default_factory=list)
    createdAt: str
    assets: list[ManifestAsset] = Field(default_factory=list)
    totalUncompressedBytes: int = Field(ge=0)
