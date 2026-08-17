import { fileUrl } from "../api";

const STATUS_LABEL = {
  generating: "생성 중",
  passed: "통과",
  failed_final: "검수 기준 미달",
};

function StatusBadge({ status, attemptCount }) {
  const label =
    status === "generating" && attemptCount > 0
      ? `재시도 중 (${attemptCount}/3)`
      : STATUS_LABEL[status];
  return <span className={`status-badge ${status}`}>{label}</span>;
}

function SlideCard({ slide }) {
  const lastAttempt = slide.attempts[slide.attempts.length - 1];
  const hasImage = slide.attempts.length > 0;
  const isRetrying = slide.status === "generating" && lastAttempt && !lastAttempt.passed;

  return (
    <div className="slide-card">
      <div className="slide-card-image">
        {hasImage ? (
          <img src={fileUrl(slide.image_url)} alt={slide.title} />
        ) : (
          <div className="slide-card-placeholder" aria-hidden="true" />
        )}
        <StatusBadge status={slide.status} attemptCount={slide.attempts.length} />
      </div>
      <div className="slide-card-body">
        <h3>{slide.title}</h3>
        <p>{slide.narration}</p>
        {isRetrying && (
          <p className="qa-note">
            QA 탈락: {lastAttempt.reason} — 프롬프트 보정 후 재생성 중...
          </p>
        )}
        {slide.status === "failed_final" && lastAttempt && (
          <p className="qa-note warning">
            최종 사유: {lastAttempt.reason} ({slide.attempts.length}회 시도 후 최선 결과)
          </p>
        )}
      </div>
    </div>
  );
}

export default function SlideTimeline({ slides }) {
  const sorted = [...slides].sort((a, b) => a.index - b.index);

  return (
    <div className="slide-gallery">
      {sorted.map((slide) => (
        <SlideCard slide={slide} key={slide.index} />
      ))}
    </div>
  );
}
