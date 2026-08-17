"""비주얼 에이전트 — 슬라이드별 image_prompt로 실제 이미지를 생성한다.

기획 에이전트(planner.py)가 슬라이드마다 서로 다른 image_prompt를 만들어주지만,
그걸 그대로 이미지 생성 API에 넘기면 슬라이드마다 그림체가 제각각이 될 수 있다.
그래서 모든 슬라이드에 공통으로 붙는 STYLE_GUIDE를 만들어 프롬프트 뒤에 항상 덧붙인다.
이렇게 하면 (1) 슬라이드 전체의 스타일이 통일되고, (2) "예쁨보다 이해"라는
디자인 원칙을 매 이미지 생성마다 강제로 지킬 수 있다.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1024"
PROMPT_FIX_MODEL = "gpt-5.4-mini"

# 모든 슬라이드 이미지에 공통으로 적용되는 스타일 제약.
# "예쁘게"가 아니라 "보자마자 이해되게"가 최우선 목표라는 걸 매번 못박는다.
# 기본은 "이미지 안에 텍스트 금지"지만, key_text가 있는 슬라이드는 TEXT_INTEGRATION_GUIDE가
# 이 규칙에 대한 명시적 예외를 덧붙인다 (아래 generate_slide_image 참고).
STYLE_GUIDE = (
    "Simple flat vector illustration style, minimal and clean. "
    "One clear focal concept only, no visual clutter or unnecessary decoration. "
    "Consistent muted corporate color palette (soft blue, gray, white) across the whole set. "
    "No embedded text, letters, or numbers inside the image — meaning must come from the imagery alone. "
    "The goal is instant comprehension at a glance, not artistic detail."
)

# key_text가 있을 때만 붙는 지시. 실험 결과 gpt-image-1은 짧은 한글 단어/숫자를 꽤
# 정확하게 그려내지만(2026-08-17 text-test 실험), 텍스트를 캔버스 위쪽 가장자리에
# 딱 붙여 배치하면 잘리는 경향이 있었다. 그래서 여백을 명시적으로 요구한다.
TEXT_INTEGRATION_GUIDE = (
    "Exception to the no-text rule above: intentionally integrate exactly this "
    "text as a deliberate design element — either a bold poster-style headline, "
    "or (if it is purely a number) a stylized 3D sculptural object: '{key_text}'. "
    "Position it with generous empty margin on all sides so it is never cropped "
    "or cut off by the image edge. Do not add any other readable text beyond this."
)


def generate_slide_image(prompt: str, output_path: str | Path, key_text: str | None = None) -> Path:
    """하나의 프롬프트로 이미지를 생성해 output_path에 PNG로 저장한다.

    key_text를 주면, 그 텍스트를 장면 안에 디자인 요소로 통합해서 그리라는
    지시가 추가된다 (기본값은 이미지 안 텍스트 완전 금지).
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    full_prompt = f"{prompt}\n\nStyle requirements: {STYLE_GUIDE}"
    if key_text:
        full_prompt += f"\n\n{TEXT_INTEGRATION_GUIDE.format(key_text=key_text)}"

    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=full_prompt,
        size=IMAGE_SIZE,
        n=1,
    )

    image_bytes = base64.b64decode(result.data[0].b64_json)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return output_path


PROMPT_FIX_INSTRUCTIONS = """\
너는 이미지 생성 프롬프트를 고치는 편집자다.
슬라이드가 원래 전달해야 하는 내용, 방금 시도한 이미지 프롬프트, 그 결과물이
왜 통과하지 못했는지에 대한 검수자 피드백, 그리고 반드시 지켜야 하는 스타일 제약을 받는다.

규칙:
- 피드백에서 지적된 문제만 구체적으로 해결하도록 프롬프트를 다시 작성하라.
- 장면 구성(무엇을 어디에 어떻게 배치할지)만 조정해서 문제를 고쳐라. 완전히 다른
  장면으로 갈아엎지 마라.
- 스타일 제약(색감, 톤, 조명, 배경 분위기)은 절대 바꾸지 마라. "더 명확하게"를
  조명 효과, 극적인 명암 대비, 어두운 배경, 강조용 글로우 같은 걸로 해결하지 마라 —
  그건 스타일 제약을 깨뜨린다. 명확함은 오직 장면 구성(무엇을 그릴지, 어떻게 배치할지)
  으로만 해결하라.
"""


class RefinedPrompt(BaseModel):
    image_prompt: str = Field(description="피드백을 반영해 다시 작성한 영어 이미지 생성 프롬프트")


def refine_image_prompt(slide, previous_prompt: str, qa_reason: str) -> str:
    """QA에서 탈락한 이유(qa_reason)를 반영해 image_prompt를 다시 작성한다."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    context = (
        f"슬라이드 제목: {slide.title}\n"
        f"나레이션: {slide.narration}\n"
        f"이전 이미지 프롬프트: {previous_prompt}\n"
        f"검수 탈락 사유: {qa_reason}\n"
        f"반드시 지켜야 하는 스타일 제약(절대 변경 금지): {STYLE_GUIDE}"
    )
    if slide.key_text:
        context += (
            f"\n이 슬라이드는 '{slide.key_text}' 텍스트를 장면에 통합해서 그리는 슬라이드다. "
            "이 텍스트 자체는 빼지 말고, 잘리거나 깨졌다면 여백을 더 주는 등 장면 구성으로 고쳐라."
        )

    response = client.responses.parse(
        model=PROMPT_FIX_MODEL,
        instructions=PROMPT_FIX_INSTRUCTIONS,
        input=context,
        text_format=RefinedPrompt,
    )
    return response.output_parsed.image_prompt


def generate_deck_images(slides, output_dir: str | Path = "outputs") -> list[Path]:
    """SlidePlan.slides 리스트를 받아 슬라이드마다 이미지를 생성하고 경로 리스트를 반환한다."""
    output_dir = Path(output_dir)
    paths = []
    for i, slide in enumerate(slides, start=1):
        path = generate_slide_image(
            slide.image_prompt, output_dir / f"slide_{i:02d}.png", key_text=slide.key_text
        )
        paths.append(path)
        print(f"슬라이드 {i} 이미지 생성 완료: {path}")
    return paths


if __name__ == "__main__":
    import sys

    from parser import extract_text
    from planner import plan_slides

    if len(sys.argv) != 2:
        print("사용법: python visualizer.py <pdf경로>")
        sys.exit(1)

    output_dir = Path("outputs")
    text = extract_text(sys.argv[1])
    plan = plan_slides(text)
    print(f"{len(plan.slides)}장의 슬라이드 기획 완료, 이미지 생성 시작...\n")
    generate_deck_images(plan.slides, output_dir)

    # QA 단계 등 후속 작업이 이미지와 슬라이드 내용(제목/나레이션)을 다시 짝지을 수 있도록 저장해둔다.
    (output_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
