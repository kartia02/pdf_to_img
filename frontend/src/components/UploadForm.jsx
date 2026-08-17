import { useState } from "react";

export default function UploadForm({ onSubmit, disabled }) {
  const [file, setFile] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (file) onSubmit(file);
  };

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files[0] ?? null)}
        disabled={disabled}
      />
      <button type="submit" disabled={!file || disabled}>
        변환 시작
      </button>
    </form>
  );
}
