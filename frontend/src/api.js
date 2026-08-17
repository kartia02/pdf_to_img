const API_BASE = "http://127.0.0.1:8000";

export async function createJob(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("업로드에 실패했습니다.");
  return res.json(); // { job_id }
}

export async function getJob(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error("작업 상태 조회에 실패했습니다.");
  return res.json();
}

export function fileUrl(path) {
  return `${API_BASE}${path}`;
}
