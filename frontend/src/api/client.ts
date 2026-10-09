import type { Album } from "../album/types";
import { getDeviceId } from "../lib/storage";
import type { ActionResult, GameState, LinkNotValidInfo } from "./types";

export class LinkNotValidError extends Error {
  constructor(public info: LinkNotValidInfo) { super("link_not_valid"); }
}
export class NetworkError extends Error { constructor() { super("network"); } }
export class HttpError extends Error {
  constructor(public status: number) { super(`http ${status}`); }
}

const base = (token: string) => `/api/play/${encodeURIComponent(token)}`;
const REQUEST_TIMEOUT_MS = 15_000;     // a stalled request on a weak signal must reach the offline banner (R-23)
const UPLOAD_TIMEOUT_MS = 120_000;     // 20 MB on a slow uplink; then "Upload failed" + Retry

async function parseError(status: number, read: () => Promise<unknown>): Promise<Error> {
  if (status === 403) {
    try {
      const body = (await read()) as { error?: LinkNotValidInfo };
      if (body.error?.code === "link_not_valid") return new LinkNotValidError(body.error);
    } catch { /* fall through */ }
  }
  return new HttpError(status);
}

async function request<T>(url: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    let res: Response;
    try {
      res = await fetch(url, {
        method: body === undefined ? "GET" : "POST",
        headers: { "X-Device-Id": getDeviceId(), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        signal: controller.signal,
      });
    } catch {
      throw new NetworkError();                 // offline, DNS, or aborted by the timeout
    }
    if (!res.ok) throw await parseError(res.status, () => res.json());
    try {
      return (await res.json()) as T;
    } catch {
      throw new NetworkError();                 // body cut off (or aborted) mid-download
    }
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  state: (token: string) => request<GameState>(base(token)),
  album: (token: string) => request<Album>(`${base(token)}/album`),   // 409 (HttpError) until the run has ended
  start: (token: string) => request<ActionResult>(`${base(token)}/start`, {}),
  answer: (token: string, position: number, answer: string) =>
    request<ActionResult>(`${base(token)}/answer`, { position, answer }),
  hint: (token: string, position: number, hint: 1 | 2) =>
    request<ActionResult>(`${base(token)}/hint`, { position, hint }),
  compass: (token: string) => request<ActionResult>(`${base(token)}/compass`, {}),
  reveal: (token: string, position: number) => request<ActionResult>(`${base(token)}/reveal`, { position }),
  rate: (token: string, position: number, stars: number) =>
    request<ActionResult>(`${base(token)}/rate`, { position, stars }),              // issue #38
  feedback: (token: string, text: string) => request<ActionResult>(`${base(token)}/feedback`, { text }),
  reset: (token: string) => request<ActionResult>(`${base(token)}/reset`, {}),   // service (test) links only
  advance: (token: string, position: number) => request<ActionResult>(`${base(token)}/advance`, { position }),
  uploadPhoto(token: string, position: number, file: File, onProgress: (pct: number) => void): Promise<ActionResult> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();                          // XHR for upload progress (PhotoUploading mock)
      xhr.open("POST", `${base(token)}/photo`);
      xhr.timeout = UPLOAD_TIMEOUT_MS;                           // otherwise ontimeout never fires
      xhr.setRequestHeader("X-Device-Id", getDeviceId());
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
      xhr.onerror = () => reject(new NetworkError());
      xhr.ontimeout = () => reject(new NetworkError());
      xhr.onabort = () => reject(new NetworkError());
      xhr.onload = async () => {
        if (xhr.status === 200) {
          // A captive portal can answer 200 with HTML. A throw inside this async handler would leave
          // the promise pending forever ("Uploading…" with Continue locked), so map it to NetworkError.
          try { resolve(JSON.parse(xhr.responseText) as ActionResult); } catch { reject(new NetworkError()); }
          return;
        }
        reject(await parseError(xhr.status, async () => JSON.parse(xhr.responseText)));
      };
      const form = new FormData();
      form.append("position", String(position));
      form.append("file", file, file.name || "photo");
      xhr.send(form);
    });
  },
};

export const isConnectionProblem = (err: unknown) =>
  err instanceof NetworkError || (err instanceof HttpError && err.status >= 500);
