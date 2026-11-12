"""Hand-authored engineering sample.

This plan exists only to exercise the renderer and media pipeline. It is NOT
evidence that image-to-video generation works, and it must never be counted as
a user acceptance sample.
"""

from __future__ import annotations

from .models import (
    ArithmeticFact,
    Chapter,
    ChoiceAnswer,
    Diagnosis,
    NarrationSegment,
    NumericAnswer,
    Option,
    PlanMeta,
    PracticeItem,
    Question,
    Scene,
    Solution,
    SolutionStep,
    TeachingPlan,
)


def build_ten_making_plan() -> TeachingPlan:
    question = Question(
        questionId="q-8-plus-5",
        questionRevision=1,
        grade=1,
        subject="math",
        knowledgePoints=["20以内加法", "凑十法"],
        questionType="singleChoice",
        stem="8 + 5 = ?",
        options=[
            Option(id="a", label="12"),
            Option(id="b", label="13"),
            Option(id="c", label="14"),
        ],
        answer=ChoiceAnswer(kind="choice", optionId="b"),
        arithmetic=[ArithmeticFact(a=8, op="+", b=5, result=13)],
        visibleWork=None,
        uncertainties=[],
        isWithinScope=True,
    )

    narrations = [
        NarrationSegment(
            id="n-title",
            text="小马陪你弄懂这道错题。先看题目：8 加 5 等于多少？",
            language="zh",
            emotion="encourage",
        ),
        NarrationSegment(
            id="n-read",
            text="题目里有 8 颗星星，还有 5 颗星星。要把它们合起来。",
            language="zh",
            emotion="explain",
        ),
        NarrationSegment(
            id="n-make",
            text="我们可以用凑十法。8 再加 2 就是 10，所以从 5 颗里拿出 2 颗。",
            language="zh",
            emotion="think",
        ),
        NarrationSegment(
            id="n-summary",
            text="8 加 2 等于 10，10 加 3 等于 13，所以 8 加 5 等于 13。",
            language="zh",
            emotion="explain",
        ),
        NarrationSegment(
            id="n-close",
            text="你学会啦！记住，先凑十，再加剩下的。",
            language="zh",
            emotion="celebrate",
        ),
    ]

    scenes = [
        Scene(
            sceneId="s-title",
            template="title",
            narrationId="n-title",
            chapterId="c-read",
            title="小马陪你学数学",
            subtitle="弄懂这道错题",
        ),
        Scene(
            sceneId="s-question",
            template="questionBoard",
            narrationId="n-read",
            chapterId="c-read",
            text="8 + 5 = ?",
        ),
        Scene(
            sceneId="s-make-ten",
            template="tenFrame",
            narrationId="n-make",
            chapterId="c-demo",
            title="凑十法",
            operands=[8, 5],
        ),
        Scene(
            sceneId="s-summary",
            template="summaryBoard",
            narrationId="n-summary",
            chapterId="c-summary",
            title="一起总结",
            expressions=["8 + 2 = 10", "10 + 3 = 13", "8 + 5 = 13"],
        ),
        Scene(
            sceneId="s-close",
            template="closing",
            narrationId="n-close",
            chapterId="c-summary",
            title="你学会啦！",
            text="先凑十，再加剩下的。",
        ),
    ]

    chapters = [
        Chapter(chapterId="c-read", title="读题", sceneId="s-title"),
        Chapter(chapterId="c-demo", title="凑十演示", sceneId="s-make-ten"),
        Chapter(chapterId="c-summary", title="总结", sceneId="s-summary"),
    ]

    practice = [
        PracticeItem(
            practiceId="p-9-plus-4",
            kind="singleChoice",
            prompt="9 + 4 = ?",
            options=[
                Option(id="a", label="12"),
                Option(id="b", label="13"),
                Option(id="c", label="14"),
            ],
            answer=ChoiceAnswer(kind="choice", optionId="b"),
            hints=["9 再加几颗就凑成 10 颗？", "从 4 里拿出 1 颗，还剩几颗？"],
            explanation="9 加 1 等于 10，10 加 3 等于 13。",
            knowledgePoints=["20以内加法", "凑十法"],
        ),
        PracticeItem(
            practiceId="p-8-plus-6",
            kind="dragDrop",
            prompt="8 + 6 = ?",
            options=[
                Option(id="a", label="13"),
                Option(id="b", label="14"),
                Option(id="c", label="15"),
            ],
            answer=NumericAnswer(kind="numeric", value=14),
            hints=["8 加 2 凑成 10。", "6 拿出 2 后还剩 4。"],
            explanation="8 加 2 等于 10，10 加 4 等于 14。",
            knowledgePoints=["20以内加法", "凑十法"],
        ),
    ]

    return TeachingPlan(
        planId="plan-demo-8-plus-5",
        question=question,
        solution=Solution(
            steps=[
                SolutionStep(
                    index=1,
                    text="先从 5 里分出 2，和 8 凑成 10。",
                    expression="8 + 2 = 10",
                ),
                SolutionStep(
                    index=2,
                    text="剩下的 3 再加到 10 上，得到 13。",
                    expression="10 + 3 = 13",
                ),
            ],
            finalAnswer="8 + 5 = 13",
            method="凑十法",
        ),
        diagnosis=Diagnosis(
            visibleError=None,
            commonMisconceptions=["把 8 加 5 算成 8 加 2，忘记加上剩下的 3。"],
        ),
        narrations=narrations,
        scenes=scenes,
        chapters=chapters,
        practice=practice,
        meta=PlanMeta(
            generator="yue-demo-handcrafted",
            model="none",
            promptVersion="demo",
            toolVersion="0.1.0",
            placeholderAudio=True,
            createdAt="",
        ),
    )
