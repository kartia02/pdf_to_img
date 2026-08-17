import { useEffect, useRef, useState } from "react";
import "./App.css";
import { createJob, getJob } from "./api";
import UploadForm from "./components/UploadForm";
import ProgressView from "./components/ProgressView";
import SlideTimeline from "./components/SlideTimeline";
import AgentLog from "./components/AgentLog";

function App() {
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const pollTimer = useRef(null);

  const handleUpload = async (file) => {
    setErrorMessage(null);
    setJob(null);
    try {
      const { job_id } = await createJob(file);
      setJobId(job_id);
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  // job_id가 생기면 그 순간부터, 일정 간격으로 서버에 "지금 어디까지 됐어?"를 계속 물어본다.
  // 이걸 폴링(polling)이라고 한다 — 파이프라인이 몇 분씩 걸리는 작업이라 한 번의
  // 요청-응답으로 끝낼 수 없어서, 진행 상황을 주기적으로 다시 확인하는 방식을 쓴다.
  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const data = await getJob(jobId);
        setJob(data);
        if (data.status === "done" || data.status === "failed") {
          clearInterval(pollTimer.current);
        }
      } catch (err) {
        setErrorMessage(err.message);
        clearInterval(pollTimer.current);
      }
    };

    poll();
    pollTimer.current = setInterval(poll, 3000);
    return () => clearInterval(pollTimer.current);
  }, [jobId]);

  const isProcessing = job && job.status !== "done" && job.status !== "failed";
  const hasSlides = job?.slides?.length > 0;

  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <span className="brand">
            <span className="brand-mark" aria-hidden="true" />
            SinglePg
          </span>
          <span className="brand-tagline">사내 문서 → 이해하기 쉬운 슬라이드</span>
        </div>
      </header>

      <div className="app">
        <section className="panel">
          <h2 className="panel-title">1. 문서 업로드</h2>
          <div className="panel-body">
            <p className="subtitle">
              PDF를 올리면 핵심 내용을 카드뉴스 스타일 슬라이드로 자동 요약합니다.
            </p>
            <UploadForm onSubmit={handleUpload} disabled={isProcessing} />
            {errorMessage && <p className="error">{errorMessage}</p>}
            {job?.status === "failed" && (
              <p className="error">처리 중 오류가 발생했습니다: {job.error}</p>
            )}
          </div>
        </section>

        {hasSlides && (
          <section className="panel">
            <h2 className="panel-title">
              2. {isProcessing ? "에이전트 작업 현황" : "결과 갤러리"}
            </h2>
            <div className="panel-body">
              {isProcessing && <ProgressView job={job} />}
              <SlideTimeline slides={job.slides} />
              <AgentLog slides={job.slides} />
            </div>
          </section>
        )}
      </div>
    </>
  );
}

export default App;
