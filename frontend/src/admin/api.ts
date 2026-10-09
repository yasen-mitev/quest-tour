import { NetworkError } from "../api/client";
import type {
  AlbumFileOut,
  AlbumRowOut,
  AssignmentCreate,
  FeedbackOut,
  AssignmentOut,
  ConflictBody,
  Game,
  GameInput,
  Landmark,
  LandmarkInput,
  Team,
  TeamInput,
  TeamPhotoOut,
  TokenReveal,
} from "./types";

const ADMIN_TIMEOUT_MS = 15_000;

export class AdminUnauthorizedError extends Error {
  constructor() {
    super("admin unauthorized");
  }
}

export type AdminValidationError = { errors: { field: string; message: string }[] };

export interface ServerErrorBody {
  reference: string;
}

export class HttpErrorWithBody extends Error {
  constructor(public status: number, public body: unknown) {
    super(`http ${status}`);
  }
}

export function isValidationError(err: unknown): err is HttpErrorWithBody {
  return err instanceof HttpErrorWithBody && err.status === 422;
}

export function isConflictError(err: unknown): err is HttpErrorWithBody {
  return err instanceof HttpErrorWithBody && err.status === 409;
}

export function isServerError(err: unknown): err is HttpErrorWithBody {
  return err instanceof HttpErrorWithBody && err.status === 500;
}

export function getServerReference(err: unknown): string | undefined {
  if (
    isServerError(err) &&
    err.body &&
    typeof err.body === "object" &&
    "reference" in err.body
  ) {
    return (err.body as ServerErrorBody).reference;
  }
  return undefined;
}

export function normalizeField(field: string): string {
  return field
    .replace(/^body\./, "")
    .replace(/^id$/, "key")
    .replace(/^reveal\./, "reveal_");
}

async function adminRequest<T>(
  url: string,
  body: unknown | undefined,
  method: "GET" | "POST" | "PUT" | "DELETE",
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ADMIN_TIMEOUT_MS);
  try {
    const init: RequestInit = {
      method,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        ...(body === undefined || body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
      },
      credentials: "include",
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
      signal: controller.signal,
    };
    let res: Response;
    try {
      res = await fetch(url, init);
    } catch {
      throw new NetworkError();
    }
    if (res.status === 401) {
      window.location.href = "/admin/login";
      throw new AdminUnauthorizedError();
    }

    let responseBody: unknown = undefined;
    try {
      responseBody = await res.json();
    } catch {
      // Non-JSON bodies are treated as no body for error shaping.
    }

    if (res.status === 422) {
      throw new HttpErrorWithBody(res.status, responseBody as AdminValidationError);
    }
    if (res.status === 409) {
      throw new HttpErrorWithBody(res.status, responseBody as ConflictBody);
    }
    if (!res.ok) {
      throw new HttpErrorWithBody(res.status, responseBody);
    }
    return responseBody as T;
  } finally {
    window.clearTimeout(timer);
  }
}

export const adminApi = {
  requestMagicLink: (email: string) =>
    adminRequest<{ url: string }>("/api/admin/auth/magic/request", { email }, "POST"),
  logout: () => adminRequest<{ ok: boolean }>("/api/admin/auth/logout", {}, "POST"),
  seedError: () => adminRequest<{ error: string | null }>("/api/admin/seed-error", undefined, "GET"),

  landmarks: () => adminRequest<Landmark[]>("/api/admin/landmarks", undefined, "GET"),
  createLandmark: (data: LandmarkInput) =>
    adminRequest<Landmark>("/api/admin/landmarks", data, "POST"),
  updateLandmark: (id: number, data: LandmarkInput & { seen_at?: string }) =>
    adminRequest<Landmark>(`/api/admin/landmarks/${id}`, data, "PUT"),
  deleteLandmark: (id: number, force = false) =>
    adminRequest<{ deleted: boolean }>(`/api/admin/landmarks/${id}?force=${force}`, undefined, "DELETE"),
  uploadLandmarkPicture: (id: number, kind: "task" | "info", file: File) => {
    const formData = new FormData();
    formData.append("kind", kind);
    formData.append("file", file);
    return adminRequest<{ blob_name: string; url: string }>(
      `/api/admin/landmarks/${id}/pictures`,
      formData,
      "POST",
    );
  },

  games: () => adminRequest<Game[]>("/api/admin/games", undefined, "GET"),
  createGame: (data: GameInput) => adminRequest<Game>("/api/admin/games", data, "POST"),
  updateGame: (id: number, data: GameInput & { seen_at?: string }) =>
    adminRequest<Game>(`/api/admin/games/${id}`, data, "PUT"),
  gameTasks: (id: number) =>
    adminRequest<{ landmark_ids: number[] }>(`/api/admin/games/${id}/tasks`, undefined, "GET"),
  updateGameTasks: (id: number, landmarkIds: number[], seenAt?: string) =>
    adminRequest<{ ok: boolean }>(`/api/admin/games/${id}/tasks`, {
      landmark_ids: landmarkIds,
      seen_at: seenAt,
    }, "PUT"),
  deleteGame: (id: number) =>
    adminRequest<{ deleted: boolean }>(`/api/admin/games/${id}`, undefined, "DELETE"),

  teams: () => adminRequest<Team[]>("/api/admin/teams", undefined, "GET"),
  createTeam: (data: TeamInput) => adminRequest<Team>("/api/admin/teams", data, "POST"),
  updateTeam: (id: number, data: TeamInput & { seen_at?: string }) =>
    adminRequest<Team>(`/api/admin/teams/${id}`, data, "PUT"),
  deleteTeam: (id: number) =>
    adminRequest<{ deleted: boolean }>(`/api/admin/teams/${id}`, undefined, "DELETE"),
  updateTeamAssignments: (id: number, assignments: AssignmentCreate[], seenAt?: string) =>
    adminRequest<TokenReveal[]>(`/api/admin/teams/${id}/assignments`, {
      assignments,
      seen_at: seenAt,
    }, "PUT"),
  teamAssignments: (teamId: number) =>
    adminRequest<AssignmentOut[]>(`/api/admin/assignments/team/${teamId}`, undefined, "GET"),
  reissueToken: (assignmentId: number) =>
    adminRequest<TokenReveal>(`/api/admin/assignments/${assignmentId}/reissue`, {}, "POST"),
  listTeamPhotos: (teamId?: number, gameId?: number) => {
    const params = new URLSearchParams();
    if (teamId !== undefined) params.set("team_id", String(teamId));
    if (gameId !== undefined) params.set("game_id", String(gameId));
    const qs = params.toString();
    return adminRequest<TeamPhotoOut[]>(`/api/admin/photos${qs ? "?" + qs : ""}`, undefined, "GET");
  },
  deleteTeamPhoto: (id: number) =>
    adminRequest<{ deleted: boolean }>(`/api/admin/photos/${id}`, undefined, "DELETE"),
  albums: () => adminRequest<AlbumRowOut[]>("/api/admin/albums", undefined, "GET"),
  feedback: () => adminRequest<FeedbackOut>("/api/admin/feedback", undefined, "GET"),
  generateAlbum: (assignmentId: number) =>
    adminRequest<AlbumFileOut>(`/api/admin/albums/${assignmentId}/generate`, {}, "POST"),
  deleteAlbum: (id: number) =>
    adminRequest<{ deleted: boolean }>(`/api/admin/albums/${id}`, undefined, "DELETE"),
};
