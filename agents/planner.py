"""기획 에이전트 — 추출된 문서 텍스트를 슬라이드 단위 구성안으로 구조화한다.

parser.py가 뽑아낸 "그냥 텍스트 덩어리"를 받아서,
LLM에게 "이걸 교육용 슬라이드 몇 장으로 나눠줘"라고 시키고
그 결과를 딱 정해진 형태(Slide, SlidePlan)로 강제해서 돌려받는다.

이렇게 결과 형태를 pydantic 모델로 미리 정의해두고 OpenAI에 넘기면
(=Structured Output), "자유 텍스트로 답하고 우리가 파싱을 다시 시도"하는
불안정한 방식 대신, 애초에 정해진 JSON 스키마로만 답하도록 모델에 강제할 수 있다.
다음 단계(비주얼 에이전트)가 이 결과를 그대로 코드에서 바로 써먹을 수 있어야 하므로 중요하다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

PLANNER_MODEL = "gpt-5.4-mini"


class Slide(BaseModel):
    title: str = Field(description="슬라이드 제목, 짧고 명확하게")
    narration: str = Field(description="이 슬라이드를 설명하는 구어체 나레이션 1~2문장")
    image_prompt: str = Field(
        description="이 슬라이드 내용을 표현할 이미지를 생성하기 위한 영어 프롬프트. "
        "구체적인 장면/구도를 묘사할 것 (예: 'a simple flat illustration of...'). "
        "key_text를 채웠다면 이 프롬프트에서 그 텍스트를 언급하지 말 것 — "
        "통합 지시는 별도로 자동 추가된다."
    )
    key_text: str | None = Field(
        default=None,
        description="슬라이드 분위기를 보여주는 짧은 제목/키워드(2~4단어 이내, 예: '재택근무', "
        "'연차 휴가')가 있으면 여기 적는다. 이미지 생성 시 이 텍스트가 장면 속 디자인 "
        "요소(포스터 헤드라인)로 통합되어 그려진다. "
        "**절대 숫자나 정확해야 하는 조건(예: '2일', '15일', '1주일 전')을 넣지 마라** — "
        "AI 이미지 생성이 숫자를 잘못 그릴 위험이 있어 정확한 정보는 나레이션 캡션이 "
        "전담해야 한다. 적절한 분위기용 제목이 없으면 null로 둔다.",
    )


class SlidePlan(BaseModel):
    slides: list[Slide]


PLANNER_INSTRUCTIONS = """\
너는 딱딱한 사내 문서를 신입 직원도 한눈에 이해할 수 있는 교육 콘텐츠로 바꾸는 기획자다.
사용자가 준 문서 텍스트를 읽고, 핵심 내용을 슬라이드 {min_slides}~{max_slides}장으로 구성하라.

슬라이드 개수 기준 (중요):
- 슬라이드 수는 원본 문서의 분량(페이지 수, 글자 수)과 무관하다. 문서가 길다고 슬라이드를 더 만들지 않는다.
- 대신 이 문서 안에 "진짜로 구분되는 핵심 주제"가 몇 개인지를 스스로 판단해서 그 개수만큼만 만든다.
- 핵심 주제가 {min_slides}개보다 적으면 무리해서 쪼개 채우지 말고, {max_slides}개보다 많으면 중요도가 낮은 것은 과감히 버린다.
- 목표는 "빠짐없이 옮겨 담기"가 아니라 "3분 안에 핵심만 이해시키기"다.

그 외 규칙:
- 각 슬라이드는 하나의 핵심 주제만 다룬다.
- narration은 문서 원문을 그대로 요약하지 말고, 실제로 옆에서 설명해주듯 구어체로 쓴다.
- image_prompt는 사진이 아니라 심플한 플랫 일러스트/다이어그램 스타일로 생성되도록 영어로 작성한다.
- 슬라이드 전체가 하나의 문서에서 나온 것처럼 스타일과 톤을 통일한다.

key_text 채우는 기준 (정확성 문제로 범위가 제한됨 — 중요):
- key_text는 "틀려도 치명적이지 않은 분위기용 제목/키워드"에만 쓴다 (예: '재택근무', '연차 휴가').
- 숫자나 정확한 조건(예: "주 2일", "15일", "1주일 전")은 key_text에 절대 넣지 않는다.
  AI 이미지 생성 모델이 숫자를 잘못 그릴 위험이 있고, 그러면 잘못된 정보가 퍼질 수 있기
  때문이다. 이런 정확한 정보는 narration에만 담아서 캡션으로 전달한다.
- 적절한 분위기용 제목이 없는 슬라이드(예: 추상적인 행동 원칙)는 key_text를 null로 둔다.
"""


def plan_slides(document_text: str, min_slides: int = 3, max_slides: int = 5) -> SlidePlan:
    """문서 텍스트를 받아 슬라이드 구성안(SlidePlan)을 반환한다.

    슬라이드 개수는 문서 분량이 아니라 문서 안 핵심 주제 개수를 기준으로 min_slides~max_slides
    범위 안에서 모델이 스스로 정한다.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.responses.parse(
        model=PLANNER_MODEL,
        instructions=PLANNER_INSTRUCTIONS.format(min_slides=min_slides, max_slides=max_slides),
        input=document_text,
        text_format=SlidePlan,
    )
    return response.output_parsed


if __name__ == "__main__":
    import sys

    from parser import extract_text

    if len(sys.argv) != 2:
        print("사용법: python planner.py <pdf경로>")
        sys.exit(1)

    text = extract_text(sys.argv[1])
    plan = plan_slides(text)

    for i, slide in enumerate(plan.slides, start=1):
        print(f"--- 슬라이드 {i}: {slide.title} ---")
        print(f"나레이션: {slide.narration}")
        print(f"핵심 텍스트: {slide.key_text}")
        print(f"이미지 프롬프트: {slide.image_prompt}")
        print()
