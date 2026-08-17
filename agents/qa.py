"""QA 에이전트 — 생성된 슬라이드 이미지가 원래 의도(핵심 주제, 즉시 이해 가능함)를
실제로 만족하는지 다시 LLM에게 평가시킨다.

이 파일은 "평가" 부분만 담당한다. 평가 결과에 따라 재생성을 반복하는
루프는 다음 단계에서 이 함수를 가져다 쓰는 쪽(파이프라인 조립부)에서 만든다.
평가 로직과 재시도 로직을 분리해야, 평가 자체가 제대로 판단하는지를
재시도 루프와 얽히지 않고 따로 검증할 수 있다.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from planner import Slide

load_dotenv()

QA_MODEL = "gpt-5.4-mini"

QA_INSTRUCTIONS = """\
너는 교육 콘텐츠의 품질을 검수하는 깐깐한 검토자다.
슬라이드 하나의 "의도된 제목/나레이션"과 실제로 생성된 이미지를 받는다.

중요한 전제: 최종 결과물에서 이 이미지는 나레이션 캡션 텍스트와 항상 나란히 표시된다
(카드뉴스 형식 — 이미지 + 캡션이 한 세트). 정확한 수치나 세부 조건(예: "주 2일",
"15일", "1주일 전")은 캡션 텍스트가 전달을 책임지므로, 이미지 혼자서 그 수치까지
정확히 표현할 필요는 없다.

다음 기준으로 이 이미지가 통과인지 판단하라 (텍스트 정확성은 별도로 검사하니 신경 쓰지 마라):
1. 이 이미지가 나레이션 캡션과 나란히 놓였을 때, 주제의 전반적인 개념/맥락을 자연스럽게
   뒷받침하는가? (정확한 수치 일치가 아니라, 큰 틀에서 내용과 어울리는지를 본다)
2. 하나의 명확한 핵심 장면만 담고 있는가? (관련 없는 요소, 산만한 디테일이 없는가)

둘 중 하나라도 어긋나면 통과시키지 말고, reason에 구체적으로 무엇이 문제인지 적어라.
"""

# 이미지 안 텍스트를 "읽어내는" 역할은 이 QA와 완전히 분리된 별도 호출에서 맡는다.
# 나레이션·기대 텍스트를 전혀 안 주고 오직 이미지 픽셀만 보고 옮겨 적게 시키는 게 핵심이다.
# (홀리스틱 호출에 나레이션과 함께 "이 텍스트 맞아?"라고 물으면, 모델이 실제 픽셀 대신
#  "나레이션에 이렇게 써있으니 이미지도 이렇겠지"라고 문맥에 기대 추측해버리는 걸 실제로 확인했다 —
#  "주 2일"을 기대했는데 이미지엔 "주 2임"이 그려졌는데도 맞다고 판정한 사례가 있었음.)
BLIND_TRANSCRIBE_INSTRUCTIONS = """\
너는 이미지 안에 어떤 텍스트가 있는지만 순수하게 옮겨 적는 역할이다.
이 이미지가 무엇에 관한 내용인지, 어떤 텍스트가 있어야 그럴듯한지에 대한 어떤 맥락도 받지 않는다.
오직 지금 보이는 이미지의 픽셀만 근거로 삼아라. 문맥을 유추하거나 "이래야 자연스럽다"고
추측하지 마라 — 실제로 그려진 글자 모양을 자모 단위까지 하나하나 그대로 옮겨 적어라.
이미지 안에 읽을 수 있는 텍스트가 있으면 정확히 그대로 옮겨 적고, 전혀 없으면 null로 답하라.
"""


class QAResult(BaseModel):
    passed: bool = Field(description="개념/장면 기준을 모두 만족하면 True, 하나라도 어긋나면 False")
    reason: str = Field(description="판단 근거를 구체적으로. 특히 탈락 시 무엇이 문제인지 명시")


class _TranscribeResult(BaseModel):
    detected_text: str | None = Field(description="이미지에서 실제로 보이는 텍스트 그대로. 없으면 null")


def _image_to_data_url(image_path: str | Path) -> str:
    image_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _transcribe_blind(image_path: str | Path) -> str | None:
    """나레이션/기대 텍스트 등 아무 맥락도 안 주고, 이미지에 실제로 보이는 텍스트만 옮겨 적게 한다."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    data_url = _image_to_data_url(image_path)

    response = client.responses.parse(
        model=QA_MODEL,
        instructions=BLIND_TRANSCRIBE_INSTRUCTIONS,
        input=[{"role": "user", "content": [{"type": "input_image", "image_url": data_url}]}],
        text_format=_TranscribeResult,
    )
    return response.output_parsed.detected_text


def evaluate_slide(image_path: str | Path, slide: Slide) -> QAResult:
    """슬라이드 이미지 하나를 원래 기획 내용(slide)에 비춰 평가한다.

    개념/장면 적합성은 나레이션까지 아는 홀리스틱 호출이 판단하고,
    텍스트 정확성은 아무 맥락도 없는 별도의 blind 호출 + 코드의 정확한 문자열 비교로 판단한다.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    data_url = _image_to_data_url(image_path)
    slide_summary = f"제목: {slide.title}\n나레이션: {slide.narration}"

    response = client.responses.parse(
        model=QA_MODEL,
        instructions=QA_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": slide_summary},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        text_format=QAResult,
    )
    result = response.output_parsed

    detected_text = _transcribe_blind(image_path)
    if slide.key_text:
        if detected_text != slide.key_text:
            result.passed = False
            result.reason = (
                f"기대한 텍스트 '{slide.key_text}'와 이미지에서 실제로 읽힌 텍스트 "
                f"'{detected_text}'가 정확히 일치하지 않음. {result.reason}"
            )
    elif detected_text is not None:
        result.passed = False
        result.reason = f"텍스트가 없어야 하는데 '{detected_text}'가 발견됨. {result.reason}"

    return result


if __name__ == "__main__":
    from planner import SlidePlan

    output_dir = Path("outputs")
    plan = SlidePlan.model_validate_json((output_dir / "plan.json").read_text(encoding="utf-8"))

    for i, slide in enumerate(plan.slides, start=1):
        image_path = output_dir / f"slide_{i:02d}.png"
        result = evaluate_slide(image_path, slide)
        status = "통과" if result.passed else "탈락"
        print(f"--- 슬라이드 {i}: {slide.title} [{status}] ---")
        print(f"근거: {result.reason}")
        print()
