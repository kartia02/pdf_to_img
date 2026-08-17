"""파이프라인 — 파싱→기획→이미지생성→QA→(탈락 시)재생성을 하나로 묶는다.

여기가 바로 "진짜 에이전트"임을 보여주는 지점이다.
단순 순차 실행이 아니라, 각 슬라이드마다 QA 결과를 보고
통과할 때까지(또는 최대 시도 횟수까지) 스스로 프롬프트를 고쳐가며 재시도한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from parser import extract_text
from planner import Slide, SlidePlan, plan_slides
from qa import QAResult, evaluate_slide
from visualizer import generate_slide_image, refine_image_prompt

MAX_RETRIES = 2  # 최초 시도 포함 총 MAX_RETRIES + 1번까지 시도


@dataclass
class SlideResult:
    index: int
    slide: Slide
    image_path: Path
    passed: bool
    attempts: int
    qa_history: list[QAResult] = field(default_factory=list)


def build_slide(slide: Slide, index: int, output_dir: Path, on_attempt=None) -> SlideResult:
    """슬라이드 하나를 이미지로 만들고, 통과할 때까지(또는 한도까지) 재시도한다.

    on_attempt(index, attempt, result, is_last_attempt)를 넘기면 매 시도(생성+QA판정)가
    끝날 때마다 호출된다. 슬라이드 하나가 통째로 끝나길 기다리지 않고, 재시도 도중에도
    "지금 몇 번째 시도 중이고 왜 탈락했는지"를 실시간으로 볼 수 있게 하기 위함이다.
    """
    prompt = slide.image_prompt
    image_path = output_dir / f"slide_{index:02d}.png"
    qa_history: list[QAResult] = []

    for attempt in range(1, MAX_RETRIES + 2):
        generate_slide_image(prompt, image_path, key_text=slide.key_text)
        result = evaluate_slide(image_path, slide)
        qa_history.append(result)
        is_last_attempt = result.passed or attempt == MAX_RETRIES + 1

        status = "통과" if result.passed else "탈락"
        print(f"  [슬라이드 {index}] 시도 {attempt}회차 — {status}: {result.reason}")

        if on_attempt:
            on_attempt(index, attempt, result, is_last_attempt)

        if result.passed:
            return SlideResult(index, slide, image_path, True, attempt, qa_history)

        if attempt <= MAX_RETRIES:
            prompt = refine_image_prompt(slide, prompt, result.reason)
            print(f"  [슬라이드 {index}] 프롬프트 보정 후 재생성...")

    return SlideResult(index, slide, image_path, False, MAX_RETRIES + 1, qa_history)


def run_pipeline(
    pdf_path: str | Path,
    output_dir: str | Path = "outputs",
    on_plan_ready=None,
    on_attempt=None,
) -> tuple[SlidePlan, list[SlideResult]]:
    """전체 파이프라인을 실행한다.

    on_plan_ready(plan), on_attempt(...)를 넘기면 각 단계가 끝날 때마다 호출된다.
    웹 서버가 이 콜백으로 작업 진행 상황을 실시간으로 기록해서 프론트엔드가
    폴링(polling)으로 진행률을 볼 수 있게 하기 위함이다.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    text = extract_text(pdf_path)
    plan = plan_slides(text)
    print(f"{len(plan.slides)}장의 슬라이드 기획 완료\n")
    if on_plan_ready:
        on_plan_ready(plan)

    results = []
    for i, slide in enumerate(plan.slides, start=1):
        print(f"슬라이드 {i}: {slide.title}")
        result = build_slide(slide, i, output_dir, on_attempt=on_attempt)
        results.append(result)
        print()

    (output_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return plan, results


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("사용법: python pipeline.py <pdf경로>")
        sys.exit(1)

    plan, results = run_pipeline(sys.argv[1])

    print("=== 최종 결과 ===")
    for r in results:
        status = "통과" if r.passed else "최종 탈락(한도 초과)"
        print(f"슬라이드 {r.index} ({r.slide.title}): {status}, 시도 {r.attempts}회")
