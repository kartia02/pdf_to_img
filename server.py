"""FastAPI 백엔드 — PDF 업로드를 받아 파이프라인을 백그라운드로 실행하고,
프론트엔드가 진행 상황과 결과를 폴링(polling)으로 확인할 수 있게 API를 제공한다.

파이프라인 한 번 실행에 몇 분씩 걸리기 때문에, 요청-응답 한 번으로 끝낼 수 없다.
그래서 (1) 업로드 요청은 즉시 job_id만 돌려주고 실제 작업은 백그라운드에서 계속 돌아가게 하고,
(2) 프론트엔드는 따로 job_id로 "지금 어디까지 됐어?"를 주기적으로 물어보는 구조로 만든다.
"""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path
from threading import Lock
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# agents/*.py 파일들은 서로를 `from parser import ...`처럼 "평범한 모듈"로 import한다.
# (agents.parser처럼 패키지 경로로 쓰지 않음) 그래서 이 파일에서 agents 안의 함수를
# 가져다 쓰려면, agents 폴더 자체를 파이썬이 모듈을 찾는 경로(sys.path)에 넣어줘야 한다.
sys.path.insert(0, str(Path(__file__).parent / "agents"))

from pipeline import run_pipeline  # noqa: E402
from planner import SlidePlan  # noqa: E402
from qa import QAResult  # noqa: E402

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SinglePg API")

# React 개발 서버(Vite, 기본 5173 포트)에서 오는 요청을 허용한다.
# 브라우저는 기본적으로 "다른 포트=다른 출처"로 보고 요청을 막는데(CORS),
# 로컬 개발 단계에서는 이걸 명시적으로 열어줘야 프론트가 API를 호출할 수 있다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# outputs/ 폴더를 /files 경로로 그대로 웹에 노출한다.
# 생성된 이미지를 프론트엔드가 <img src="http://.../files/{job_id}/slide_01.png">로 바로 불러오게 하기 위함.
app.mount("/files", StaticFiles(directory=OUTPUT_DIR), name="files")


class QaAttemptOut(BaseModel):
    attempt: int
    passed: bool
    reason: str


class SlideOut(BaseModel):
    index: int
    title: str
    narration: str
    status: Literal["generating", "passed", "failed_final"] = "generating"
    attempts: list[QaAttemptOut] = []
    image_url: str


class JobState(BaseModel):
    status: Literal["pending", "running", "done", "failed"] = "pending"
    total_slides: Optional[int] = None
    slides: list[SlideOut] = []
    error: Optional[str] = None


# 데모용 최소 구성이라 별도 데이터베이스 없이 메모리(dict)에 job 상태를 둔다.
# 서버가 재시작되면 기록이 날아가지만, 로컬 데모 목적이라 문제 없음.
JOBS: dict[str, JobState] = {}
_lock = Lock()


def _run_job(job_id: str, pdf_path: Path) -> None:
    job_dir = OUTPUT_DIR / job_id

    def on_plan_ready(plan: SlidePlan) -> None:
        with _lock:
            JOBS[job_id].status = "running"
            JOBS[job_id].total_slides = len(plan.slides)
            # 슬라이드 전체를 미리 "생성 중" 상태로 채워둔다. 그래야 프론트가
            # 아직 시작도 안 한 슬라이드까지 포함해서 전체 타임라인을 바로 보여줄 수 있다.
            JOBS[job_id].slides = [
                SlideOut(
                    index=i,
                    title=s.title,
                    narration=s.narration,
                    status="generating",
                    attempts=[],
                    image_url=f"/files/{job_id}/slide_{i:02d}.png",
                )
                for i, s in enumerate(plan.slides, start=1)
            ]

    def on_attempt(index: int, attempt: int, result: QAResult, is_last_attempt: bool) -> None:
        with _lock:
            slide_out = JOBS[job_id].slides[index - 1]
            slide_out.attempts.append(
                QaAttemptOut(attempt=attempt, passed=result.passed, reason=result.reason)
            )
            if result.passed:
                slide_out.status = "passed"
            elif is_last_attempt:
                slide_out.status = "failed_final"
            else:
                slide_out.status = "generating"
            # 재생성될 때마다 이미지 파일 내용이 바뀌므로, 쿼리스트링을 붙여 브라우저가
            # 캐시된 이전 이미지를 계속 보여주지 않고 다시 받아오게 한다.
            slide_out.image_url = f"/files/{job_id}/slide_{index:02d}.png?v={attempt}"

    try:
        run_pipeline(
            pdf_path,
            output_dir=job_dir,
            on_plan_ready=on_plan_ready,
            on_attempt=on_attempt,
        )
        with _lock:
            JOBS[job_id].status = "done"
    except Exception as e:  # noqa: BLE001 — 백그라운드 작업 실패를 API 응답으로 그대로 전달하기 위함
        with _lock:
            JOBS[job_id].status = "failed"
            JOBS[job_id].error = str(e)
    finally:
        pdf_path.unlink(missing_ok=True)


@app.post("/jobs")
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    pdf_path = UPLOAD_DIR / f"{job_id}.pdf"
    with pdf_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    JOBS[job_id] = JobState()
    background_tasks.add_task(_run_job, job_id, pdf_path)
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return {"error": "존재하지 않는 job_id"}
    return job
