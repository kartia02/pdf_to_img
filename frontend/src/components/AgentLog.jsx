export default function AgentLog({ slides }) {
  const entries = slides
    .flatMap((slide) =>
      slide.attempts.map((a) => ({
        index: slide.index,
        title: slide.title,
        ...a,
      }))
    )
    .sort((a, b) => a.index - b.index || a.attempt - b.attempt);

  if (entries.length === 0) return null;

  return (
    <div className="agent-log">
      <h3>에이전트 활동 로그</h3>
      <ul>
        {entries.map((e) => (
          <li key={`${e.index}-${e.attempt}`} className={e.passed ? "log-pass" : "log-fail"}>
            <span className="log-slide">슬라이드 {e.index}</span>
            <span className="log-msg">
              {e.attempt}회차 — {e.passed ? "통과" : `탈락: ${e.reason}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
