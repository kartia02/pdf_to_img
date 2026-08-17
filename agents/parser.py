"""문서 파싱 에이전트 — PDF에서 텍스트를 페이지 단위로 추출한다.

의미 단위 구조화(섹션 나누기, 핵심 포인트 뽑기)는 여기서 하지 않는다.
그 작업은 LLM을 쓰는 기획 에이전트(planner.py)의 몫이다.
이 모듈은 순수 기계적 추출만 담당한다.
"""

from pathlib import Path

from pypdf import PdfReader


def extract_pages(pdf_path: str | Path) -> list[str]:
    """PDF를 읽어 페이지별 텍스트 리스트를 반환한다."""
    reader = PdfReader(pdf_path)
    return [page.extract_text() or "" for page in reader.pages]


def extract_text(pdf_path: str | Path) -> str:
    """PDF 전체 텍스트를 페이지 구분 없이 하나로 이어붙여 반환한다."""
    return "\n\n".join(extract_pages(pdf_path))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("사용법: python parser.py <pdf경로>")
        sys.exit(1)

    pages = extract_pages(sys.argv[1])
    print(f"총 {len(pages)}페이지 추출됨\n")
    for i, page_text in enumerate(pages, start=1):
        print(f"--- {i}페이지 ({len(page_text)}자) ---")
        print(page_text[:300])
        print()
