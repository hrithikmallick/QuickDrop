import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { formatBytes, formatTime, getDownloadMeta, type DownloadMeta } from "../api";
import Brand from "../components/Brand";

export default function Download() {
  const { token } = useParams();
  const [meta, setMeta] = useState<DownloadMeta | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    getDownloadMeta(token)
      .then(setMeta)
      .catch((err: Error) => setError(err.message));
  }, [token]);

  return (
    <main className="download-page">
      <header className="download-header"><Brand compact /></header>
      <section className="download-card">
        {!meta && !error && <><span className="spinner" /><p className="muted">Preparing your file…</p></>}
        {error && (
          <div className="download-state">
            <span className="download-file-icon error-icon" aria-hidden="true">!</span>
            <p className="section-kicker">Link unavailable</p>
            <h1>This file is no longer here</h1>
            <p className="muted">{error}</p>
          </div>
        )}
        {meta && (
          <div className="download-state">
            <span className="download-file-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none"><path d="M7 3.5h6.5L18 8v12.5H7z" /><path d="M13 3.5V8h5" /></svg>
            </span>
            <p className="section-kicker">A file was shared with you</p>
            <h1>{meta.filename}</h1>
            <div className="download-meta">
              <span>{formatBytes(meta.size_bytes)}</span>
              <i />
              <span>Expires {formatTime(meta.expires_at)}</span>
            </div>
            {meta.delete_after_download && (
              <div className="one-time-warning">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3 5 6v5c0 4.7 2.9 8.2 7 10 4.1-1.8 7-5.3 7-10V6l-7-3Z" /><path d="M12 8v4m0 4h.01" /></svg>
                <span><strong>One-time download</strong>This link expires when the download starts.</span>
              </div>
            )}
            <a className="download-button" href={meta.download_url}>
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 4v12m0 0 4.5-4.5M12 16l-4.5-4.5" /><path d="M5 19.5h14" /></svg>
              Download file
            </a>
            <p className="download-footnote">Shared securely with QuickDrop</p>
          </div>
        )}
      </section>
    </main>
  );
}
