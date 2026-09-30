import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type DragEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  completeUpload,
  deleteFile,
  formatBytes,
  formatTime,
  getMe,
  initUpload,
  listFiles,
  logout,
  shareFile,
  uploadWithProgress,
  type FileRow,
  type Me,
} from "../api";
import Brand from "../components/Brand";

const EXPIRY_OPTIONS = [
  { value: "1h", label: "1 hour" },
  { value: "6h", label: "6 hours" },
  { value: "24h", label: "24 hours" },
  { value: "3d", label: "3 days" },
  { value: "7d", label: "7 days" },
];

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
      <path d="M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M7 3.5h6.5L18 8v12.5H7z" />
      <path d="M13 3.5V8h5" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" />
      <path d="M10 11v5m4-5v5" />
    </svg>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [files, setFiles] = useState<FileRow[]>([]);
  const [expiry, setExpiry] = useState("24h");
  const [deleteAfterDownload, setDeleteAfterDownload] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const user = await getMe();
    if (!user) {
      navigate("/login");
      return;
    }
    setMe(user);
    setFiles(await listFiles());
  }, [navigate]);

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [refresh]);

  const usedPct = useMemo(() => {
    if (!me) return 0;
    return Math.min(100, (me.storage_used_bytes / me.storage_limit_bytes) * 100);
  }, [me]);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  async function uploadFile(file: File) {
    setError("");
    setStatus(`Uploading ${file.name}`);
    setBusy(true);
    setProgress(0);
    try {
      const init = await initUpload({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        expiry,
        delete_after_download: deleteAfterDownload,
      });
      await uploadWithProgress(init.upload_url, file, init.headers || {}, setProgress);
      await completeUpload(init.id);
      setStatus("Upload complete");
      setProgress(100);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setOver(false);
    if (busy) return;
    const file = event.dataTransfer.files[0];
    if (file) void uploadFile(file);
  }

  async function onShare(id: string) {
    setError("");
    setProgress(null);
    try {
      const result = await shareFile(id);
      await navigator.clipboard.writeText(result.share_url);
      setStatus("Share link copied to clipboard");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Share failed");
    }
  }

  async function onDelete(id: string) {
    setError("");
    setProgress(null);
    try {
      await deleteFile(id);
      setStatus("File deleted");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (!me) {
    return (
      <div className="loading-screen">
        <span className="spinner" />
        <p>Opening your drop space…</p>
      </div>
    );
  }

  const identity = me.display_name || me.email || "Your account";
  const initial = identity.trim().charAt(0).toUpperCase() || "Q";

  return (
    <div className="app-shell">
      <header className="app-header">
        <Brand compact />
        <div className="account-menu">
          <span className="avatar" aria-hidden="true">{initial}</span>
          <span className="account-copy">
            <strong>{me.display_name || "Signed in"}</strong>
            <small>{me.email}</small>
          </span>
          <button className="icon-button logout-button" onClick={handleLogout} aria-label="Log out" title="Log out">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M10 5H6.5A2.5 2.5 0 0 0 4 7.5v9A2.5 2.5 0 0 0 6.5 19H10" />
              <path d="M14 8l4 4-4 4m4-4H9" />
            </svg>
          </button>
        </div>
      </header>

      <main>
        <section className="dashboard-intro">
          <p className="eyebrow">Private file delivery</p>
          <h1>Send it. Share it. <span>Let it disappear.</span></h1>
          <p>Upload directly to private storage and decide how long every file should live.</p>
        </section>

        <div className="dashboard-layout">
          <section className="panel upload-panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">New upload</p>
                <h2>Drop a file</h2>
              </div>
              <span className="limit-badge">Up to 500 MiB</span>
            </div>

            <div className="upload-options">
              <label className="field-control">
                <span>Link expiry</span>
                <select value={expiry} onChange={(event) => setExpiry(event.target.value)} disabled={busy}>
                  {EXPIRY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>

              <label className="toggle-option">
                <input
                  type="checkbox"
                  checked={deleteAfterDownload}
                  onChange={(event) => setDeleteAfterDownload(event.target.checked)}
                  disabled={busy}
                />
                <span className="toggle-track" aria-hidden="true"><span /></span>
                <span className="toggle-copy">
                  <strong>Expire after first download</strong>
                  <small>The share link works once</small>
                </span>
              </label>
            </div>

            <label
              className={`drop-zone${over ? " is-over" : ""}${busy ? " is-busy" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                if (!busy) setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={onDrop}
            >
              <input
                type="file"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.currentTarget.value = "";
                  if (file) void uploadFile(file);
                }}
              />
              <span className="upload-icon"><UploadIcon /></span>
              <strong>{busy ? "Uploading securely…" : "Drag and drop your file here"}</strong>
              <span>or <b>browse from your device</b></span>
            </label>

            {progress !== null && (
              <div className="upload-progress" aria-live="polite">
                <div className="progress-copy">
                  <span>{status || "Uploading"}</span>
                  <strong>{progress}%</strong>
                </div>
                <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
              </div>
            )}
            {status && progress === null && <p className="notice success" role="status">{status}</p>}
            {error && <p className="notice error" role="alert">{error}</p>}
          </section>

          <aside className="panel storage-panel">
            <div className="panel-heading compact-heading">
              <div>
                <p className="section-kicker">Your space</p>
                <h2>Storage</h2>
              </div>
              <span className="storage-percent">{Math.round(usedPct)}%</span>
            </div>
            <div
              className="storage-ring"
              style={{ "--storage-angle": `${usedPct * 3.6}deg` } as CSSProperties}
              aria-label={`${Math.round(usedPct)} percent of storage used`}
            >
              <div>
                <strong>{formatBytes(me.storage_used_bytes)}</strong>
                <span>of {formatBytes(me.storage_limit_bytes)}</span>
              </div>
            </div>
            <div className="storage-details">
              <span><i className="dot used" />Used</span>
              <strong>{formatBytes(me.storage_used_bytes)}</strong>
              <span><i className="dot free" />Available</span>
              <strong>{formatBytes(me.storage_available_bytes)}</strong>
              {me.storage_reserved_bytes > 0 && (
                <><span><i className="dot reserved" />Reserved</span><strong>{formatBytes(me.storage_reserved_bytes)}</strong></>
              )}
            </div>
          </aside>
        </div>

        <section className="panel files-panel">
          <div className="panel-heading files-heading">
            <div>
              <p className="section-kicker">Manage</p>
              <h2>Your files</h2>
            </div>
            <span className="file-count">{files.length} {files.length === 1 ? "file" : "files"}</span>
          </div>

          {files.length === 0 ? (
            <div className="empty-files">
              <span className="empty-icon"><FileIcon /></span>
              <h3>No files here yet</h3>
              <p>Your uploads will appear here, ready to share.</p>
            </div>
          ) : (
            <div className="file-list">
              {files.map((file) => (
                <article className="file-row" key={file.id}>
                  <span className="file-icon"><FileIcon /></span>
                  <div className="file-copy">
                    <div className="file-title-row">
                      <h3>{file.filename}</h3>
                      {file.delete_after_download && <span className="one-time-badge">One-time</span>}
                    </div>
                    <p>{formatBytes(file.size_bytes)} <i /> Expires {formatTime(file.expires_at)}</p>
                  </div>
                  <div className="file-actions">
                    {file.status === "ACTIVE" && (
                      <button className="action-button share" onClick={() => onShare(file.id)}>
                        <CopyIcon /> <span>Copy link</span>
                      </button>
                    )}
                    <button className="action-button delete" onClick={() => onDelete(file.id)} aria-label={`Delete ${file.filename}`}>
                      <TrashIcon /> <span>Delete</span>
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
