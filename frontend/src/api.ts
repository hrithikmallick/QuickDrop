export type Me = {
  id: string;
  email: string | null;
  display_name: string | null;
  storage_used_bytes: number;
  storage_reserved_bytes: number;
  storage_limit_bytes: number;
  storage_available_bytes: number;
};

export type FileRow = {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: string;
  expires_at: number | null;
  created_at: number;
  updated_at: number;
  has_share: boolean;
  delete_after_download: boolean;
};

export type DownloadMeta = {
  filename: string;
  content_type: string | null;
  size_bytes: number;
  expires_at: number | null;
  download_url: string;
  download_mode: string;
  expires_in: number;
  delete_after_download: boolean;
};

async function parse(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || res.statusText;
    throw new Error(detail);
  }
  return data;
}

export async function getMe(): Promise<Me | null> {
  const res = await fetch("/api/me", { credentials: "include" });
  if (res.status === 401) return null;
  return (await parse(res)) as Me;
}

export async function listFiles(): Promise<FileRow[]> {
  const res = await fetch("/api/files", { credentials: "include" });
  const data = (await parse(res)) as { files: FileRow[] };
  return data.files;
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
}

export async function initUpload(input: {
  filename: string;
  content_type: string;
  size_bytes: number;
  expiry: string;
  delete_after_download: boolean;
}) {
  const res = await fetch("/api/uploads/init", {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
  return parse(res) as Promise<{
    id: string;
    upload_url: string;
    upload_mode: string;
    headers: Record<string, string>;
  }>;
}

export async function completeUpload(id: string): Promise<FileRow> {
  const res = await fetch(`/api/uploads/${id}/complete`, {
    method: "POST",
    credentials: "include",
  });
  return parse(res) as Promise<FileRow>;
}

export async function shareFile(id: string): Promise<{ share_url: string }> {
  const res = await fetch(`/api/files/${id}/share`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  return parse(res) as Promise<{ share_url: string }>;
}

export async function deleteFile(id: string): Promise<void> {
  const res = await fetch(`/api/files/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  await parse(res);
}

export async function getDownloadMeta(token: string): Promise<DownloadMeta> {
  const res = await fetch(`/api/d/${token}`);
  return parse(res) as Promise<DownloadMeta>;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function formatTime(ts: number | null): string {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString();
}

export function uploadWithProgress(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (pct: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.withCredentials = url.startsWith("/") || url.startsWith(window.location.origin);
    Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.send(file);
  });
}
