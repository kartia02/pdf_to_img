"""파이프라인 — 파싱→기획→이미지생성→QA→(탈락 시)재생성을 하나로 묶는다.

여기가 바로 "진짜 에이전트"임을 보여주는 지점이다.
단순 순차 실행이 아니라, 각 슬라이드마다 QA 결과를 보고
통과할 때까지(또는 최대 시도 횟수까지) 스스로 프롬프트를 고쳐가며 재시도한다.

이 파일은 두 층으로 나뉜다:

    run_pipeline()      1층 — 전체 작업: 파싱 → 기획 → 슬라이드마다 build_slide 호출
      └ build_slide()   2층 — 슬라이드 "한 장": 생성 → QA → 탈락 시 보정 후 재생성

"한 장 만들기"를 따로 떼어낸 이유는 재시도가 슬라이드 단위로 일어나야 하기 때문이다.
3번 슬라이드가 탈락했다고 1·2번까지 다시 만들 이유는 없다.
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

        # ★ 이 프로젝트의 핵심 차별점 — 같은 프롬프트로 무작정 다시 시도하는 게 아니라,
        #   QA가 준 탈락 사유(result.reason)를 LLM에게 다시 넘겨 프롬프트를 고쳐 쓰게 한다.
        #   "단순 retry"와 "에이전트"를 가르는 지점이 정확히 여기다.
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

    # ── 1) 파싱: PDF에서 글자만 기계적으로 긁어온다 (의미 판단 없음) ──
    text = extract_text(pdf_path)

    # ── 2) 기획: 여기서 plan이 완성된다 ──
    #   plan 안에는 슬라이드별로 제목 / 나레이션 / 이미지 프롬프트 / key_text가
    #   전부 채워져 있다. 즉 "무엇을 만들지에 대한 완전한 설계도". 이미지는 아직 0장.
    plan = plan_slides(text)
    print(f"{len(plan.slides)}장의 슬라이드 기획 완료\n")

    # ── ✂ 이음매: 기획은 끝났고 이미지는 아직 안 만든 시점 ──
    #   원래는 "기획 끝났다"고 바깥(서버)에 알리기만 하는 자리였다.
    #   ▶ 사람 승인 단계를 넣는다면 바로 여기다 — 알리는 데서 멈추고
    #     "이 기획안대로 진행해도 되나?"에 대한 답을 기다리도록 확장하면 된다.
    if on_plan_ready:
        on_plan_ready(plan)

    # ── 3) 이미지 생성: 여기서부터 비용과 시간의 대부분이 발생한다 ──
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
