import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  adminApi,
  AdminUnauthorizedError,
  getServerReference,
  HttpErrorWithBody,
  isConflictError,
  isServerError,
  isValidationError,
} from "./api";

const makeFetch = (res: Partial<Response> & { json?: () => Promise<unknown> }) =>
  vi.fn(async () => res as Response);

beforeEach(() => {
  vi.stubGlobal("fetch", makeFetch({ ok: true, json: async () => null }));
  vi.stubGlobal("location", { href: "" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastFetchCall(): [string, RequestInit] {
  const calls = vi.mocked(globalThis.fetch).mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  return calls[calls.length - 1] as [string, RequestInit];
}

describe("adminRequest", () => {
  it("sends credentials include and X-Requested-With on every request", async () => {
    await adminApi.seedError();
    const [, options] = lastFetchCall();
    expect(options.credentials).toBe("include");
    expect(options.headers).toMatchObject({ "X-Requested-With": "XMLHttpRequest" });
  });

  it("does not send Content-Type or body for GET", async () => {
    await adminApi.seedError();
    const [, options] = lastFetchCall();
    expect(options.method).toBe("GET");
    expect(options.body).toBeUndefined();
    expect(options.headers).not.toHaveProperty("Content-Type");
  });

  it("uses explicit method for PUT", async () => {
    await adminApi.updateLandmark(1, {
      key: "old-town",
      name: "Old Town",
      name_i18n: null,
      task: "Find the statue",
      task_i18n: null,
      accepted_answers: ["statue"],
      hint1: null,
      hint1_i18n: null,
      hint2: null,
      hint2_i18n: null,
      tourist_info: "Historic center",
      tourist_info_i18n: null,
      coordinates: null,
    });
    const [, options] = lastFetchCall();
    expect(options.method).toBe("PUT");
    expect(options.body).toBe(JSON.stringify({
      key: "old-town",
      name: "Old Town",
      name_i18n: null,
      task: "Find the statue",
      task_i18n: null,
      accepted_answers: ["statue"],
      hint1: null,
      hint1_i18n: null,
      hint2: null,
      hint2_i18n: null,
      tourist_info: "Historic center",
      tourist_info_i18n: null,
      coordinates: null,
    }));
  });

  it("uses explicit method for DELETE", async () => {
    await adminApi.deleteLandmark(7);
    const [url, options] = lastFetchCall();
    expect(options.method).toBe("DELETE");
    expect(url).toBe("/api/admin/landmarks/7?force=false");
    expect(options.body).toBeUndefined();
  });

  it("sends force=true query param when deleting landmark", async () => {
    await adminApi.deleteLandmark(7, true);
    const [url] = lastFetchCall();
    expect(url).toBe("/api/admin/landmarks/7?force=true");
  });

  it("sends POST with empty body for logout", async () => {
    await adminApi.logout();
    const [, options] = lastFetchCall();
    expect(options.method).toBe("POST");
    expect(options.body).toBe("{}");
    expect(options.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("sends POST with empty body for reissueToken", async () => {
    await adminApi.reissueToken(42);
    const [url, options] = lastFetchCall();
    expect(url).toBe("/api/admin/assignments/42/reissue");
    expect(options.method).toBe("POST");
    expect(options.body).toBe("{}");
  });

  it("throws NetworkError when fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    const { NetworkError } = await import("../api/client");
    await expect(adminApi.seedError()).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("error handling", () => {
  it("redirects to /admin/login and throws AdminUnauthorizedError on 401", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetch({ status: 401, ok: false, json: async () => ({ detail: "unauthorized" }) })
    );
    await expect(adminApi.seedError()).rejects.toBeInstanceOf(AdminUnauthorizedError);
    expect(window.location.href).toBe("/admin/login");
  });

  it("throws HttpErrorWithBody with validation errors on 422", async () => {
    const body = { errors: [{ field: "key", message: "already exists" }] };
    vi.stubGlobal("fetch", makeFetch({ status: 422, ok: false, json: async () => body }));
    await expect(adminApi.createLandmark({
      key: "dup",
      name: "Dup",
      name_i18n: null,
      task: "x",
      task_i18n: null,
      accepted_answers: ["x"],
      hint1: null,
      hint1_i18n: null,
      hint2: null,
      hint2_i18n: null,
      tourist_info: "x",
      tourist_info_i18n: null,
      coordinates: null,
    })).rejects.toBeInstanceOf(HttpErrorWithBody);
    try {
      await adminApi.createLandmark({
        key: "dup",
        name: "Dup",
        name_i18n: null,
        task: "x",
        task_i18n: null,
        accepted_answers: ["x"],
        hint1: null,
        hint1_i18n: null,
        hint2: null,
        hint2_i18n: null,
        tourist_info: "x",
        tourist_info_i18n: null,
        coordinates: null,
      });
    } catch (err) {
      expect(isValidationError(err)).toBe(true);
      if (isValidationError(err)) {
        expect(err.body).toEqual(body);
      }
    }
  });

  it("throws HttpErrorWithBody with conflict body on 409", async () => {
    const body = { entity: "Landmark", current: { id: 1, updated_at: "2026-10-07T10:00:00Z" } };
    vi.stubGlobal("fetch", makeFetch({ status: 409, ok: false, json: async () => body }));
    try {
      await adminApi.updateLandmark(1, {
        key: "old-town",
        name: "Old Town",
        name_i18n: null,
        task: "Find the statue",
        task_i18n: null,
        accepted_answers: ["statue"],
        hint1: null,
        hint1_i18n: null,
        hint2: null,
        hint2_i18n: null,
        tourist_info: "Historic center",
        tourist_info_i18n: null,
        coordinates: null,
      });
    } catch (err) {
      expect(isConflictError(err)).toBe(true);
      if (isConflictError(err)) {
        expect(err.body).toEqual(body);
      }
    }
  });

  it("exposes reference from 500 body via getServerReference", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetch({ status: 500, ok: false, json: async () => ({ reference: "ref-abc-123" }) })
    );
    try {
      await adminApi.seedError();
    } catch (err) {
      expect(isServerError(err)).toBe(true);
      expect(getServerReference(err)).toBe("ref-abc-123");
    }
  });

  it("wraps other errors in HttpErrorWithBody", async () => {
    vi.stubGlobal("fetch", makeFetch({ status: 418, ok: false, json: async () => ({}) }));
    await expect(adminApi.seedError()).rejects.toBeInstanceOf(HttpErrorWithBody);
  });
});

describe("team photos query params", () => {
  it("builds URL with team_id and game_id filters", async () => {
    await adminApi.listTeamPhotos(3, 5);
    const [url] = lastFetchCall();
    expect(url).toBe("/api/admin/photos?team_id=3&game_id=5");
    const [, options] = lastFetchCall();
    expect(options.method).toBe("GET");
  });

  it("omits query string when no filters", async () => {
    await adminApi.listTeamPhotos();
    const [url] = lastFetchCall();
    expect(url).toBe("/api/admin/photos");
  });
});

describe("game requests", () => {
  it("lists pending requests by default and other statuses on request", async () => {
    await adminApi.gameRequests();
    expect(lastFetchCall()[0]).toBe("/api/admin/requests?status=pending");
    await adminApi.gameRequests("all");
    expect(lastFetchCall()[0]).toBe("/api/admin/requests?status=all");
  });

  it("posts seen_at to approve and reject", async () => {
    await adminApi.approveGameRequest(5, "2026-11-01T09:00:00Z");
    let [url, options] = lastFetchCall();
    expect(url).toBe("/api/admin/requests/5/approve");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual({ seen_at: "2026-11-01T09:00:00Z" });

    await adminApi.rejectGameRequest(5, "2026-11-01T09:00:00Z");
    [url, options] = lastFetchCall();
    expect(url).toBe("/api/admin/requests/5/reject");
    expect(options.method).toBe("POST");
  });

  it("puts edits to the request", async () => {
    await adminApi.updateGameRequest(5, { game_id: 10, exit_message: null, teams: [] });
    const [url, options] = lastFetchCall();
    expect(url).toBe("/api/admin/requests/5");
    expect(options.method).toBe("PUT");
  });
});
