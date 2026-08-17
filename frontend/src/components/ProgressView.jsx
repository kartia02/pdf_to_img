export default function ProgressView({ job }) {
  const total = job.total_slides ?? 0;
  const finalized = job.slides.filter((s) => s.status !== "generating").length;

  return (
    <div className="progress-view">
      <p>
        {total > 0
          ? `슬라이드 검수 진행 중... (${finalized}/${total} 완료)`
          : "문서 분석하고 슬라이드 기획하는 중..."}
      </p>
      {total > 0 && (
        <div className="progress-bar">
          <div
            className="progress-bar-fill"
            style={{ width: `${(finalized / total) * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
