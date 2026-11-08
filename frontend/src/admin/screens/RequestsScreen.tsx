import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import {
  adminApi,
  getServerReference,
  HttpErrorWithBody,
  isConflictError,
  isServerError,
  isValidationError,
  normalizeField,
} from "../api";
import type { AdminValidationError } from "../api";
import { REQUESTS_CHANGED } from "../components/AdminLayout";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FieldErrorList } from "../components/FieldErrorList";
import { TokenLink } from "../components/TokenLink";
import type {
  Game,
  GameRequestDetail,
  GameRequestFilter,
  GameRequestListItem,
  GameRequestStatus,
  GameRequestUpdate,
  TokenReveal,
} from "../types";

type FieldErrors = AdminValidationError["errors"];

/** A team row as edited: windows are local times in the game's time zone, "" = not set. */
type TeamRow = {
  name: string;
  key: string;
  participants: string;
  valid_from: string;
  valid_until: string;
  team_id: number | null;
};

type RequestForm = { game_id: string; exit_message: string; teams: TeamRow[] };

const STATUS_LABEL: Record<GameRequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};

const FILTERS: { value: GameRequestFilter; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

/** The play-date default window (D1), as local times in the game's time zone. */
const DEFAULT_FROM = "00:00:00";
const DEFAULT_UNTIL = "23:59:59";

/** Fields shown next to their input; any other error goes to the list at the top. */
const INLINE_FIELD = /^(game_id|exit_message|teams\.\d+\.(name|key|participants|valid_from|valid_until))$/;

function teamsLabel(count: number): string {
  return count === 1 ? "1 team" : `${count} teams`;
}

/** A UTC instant as a datetime-local value in `timeZone` (seconds only when not zero). */
function zonedLocal(iso: string, timeZone: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((part) => [part.type, part.value]),
  );
  const seconds = parts.second === "00" ? "" : `:${parts.second}`;
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}${seconds}`;
}

function toForm(detail: GameRequestDetail): RequestForm {
  const zone = detail.game_time_zone;
  const local = (value: string | null) => (value && zone ? zonedLocal(value, zone) : "");
  return {
    game_id: detail.game_id === null ? "" : String(detail.game_id),
    exit_message: detail.exit_message,
    teams: detail.teams.map((team) => ({
      name: team.name,
      key: team.key,
      participants: team.participants === null ? "" : String(team.participants),
      valid_from: local(team.valid_from),
      valid_until: local(team.valid_until),
      team_id: team.team_id,
    })),
  };
}

/** A window bound as sent: null when empty or left at the play-date default, so it follows the game. */
function windowOut(value: string, playDate: string, defaultTime: string): string | null {
  if (!value) return null;
  // Inputs report "HH:MM" when the seconds are zero, and may add ".000" to the seconds.
  const normal = (value.length === 16 ? `${value}:00` : value).slice(0, 19);
  return normal === `${playDate}T${defaultTime}` ? null : value;
}

function toUpdate(form: RequestForm, detail: GameRequestDetail): GameRequestUpdate {
  return {
    game_id: Number(form.game_id),
    exit_message: form.exit_message,
    teams: form.teams.map((team) => ({
      name: team.name,
      key: team.key,
      participants: team.participants.trim() === "" ? null : Number(team.participants),
      valid_from: windowOut(team.valid_from, detail.play_date, DEFAULT_FROM),
      valid_until: windowOut(team.valid_until, detail.play_date, DEFAULT_UNTIL),
    })),
    seen_at: detail.updated_at,
  };
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function RequestsScreen({ subPath }: { subPath: string }) {
  const segment = subPath.split("/").filter(Boolean)[1];
  if (segment === undefined) return <RequestList />;
  return <RequestDetailView id={Number(segment)} />;
}

function RequestList() {
  const [status, setStatus] = useState<GameRequestFilter>("pending");
  const [rows, setRows] = useState<GameRequestListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminApi
      .gameRequests(status)
      .then((next) => {
        if (!cancelled) setRows(next);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load requests.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  return (
    <div className="admin-section">
      <h1 className="t-title">Requests</h1>
      <div className="admin-filters">
        <label className="qc-field">
          <span className="qc-field__label">Status</span>
          <select
            className="qc-input"
            value={status}
            onChange={(e) => setStatus(e.target.value as GameRequestFilter)}
            aria-label="Status"
          >
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="qc-field__error">{error}</p>}
      {loading ? (
        <p className="t-body">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="t-body">{status === "all" ? "No requests." : `No ${status} requests.`}</p>
      ) : (
        <ul className="admin-list">
          {rows.map((r) => (
            <li key={r.id} className="admin-list-item">
              <div>
                <strong className="t-body">{r.contact_name}</strong>
                <span className="t-caption">
                  {" "}
                  — {r.game_name ?? "Game removed"} · {r.play_date} · {teamsLabel(r.team_count)}
                </span>
                <div className="t-caption">
                  {STATUS_LABEL[r.status]} · received {formatTime(r.created_at)}
                </div>
              </div>
              <div className="admin-row-actions">
                <a className="qc-btn qc-btn--secondary" href={`/admin/requests/${r.id}`}>
                  Open
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A labelled input with its inline errors, in the qc-field layout used by EntityForm. */
function Field({
  id,
  label,
  errors,
  children,
}: {
  id: string;
  label: string;
  errors: FieldErrors;
  children: ReactNode;
}) {
  return (
    <div className={`qc-field ${errors.length ? "qc-field--error" : ""}`}>
      <label className="qc-field__label" htmlFor={id}>
        {label}
      </label>
      {children}
      {errors.map((err) => (
        <p key={err.message} id={`${id}-error`} className="qc-field__error">
          {err.message}
        </p>
      ))}
    </div>
  );
}

function RequestDetailView({ id }: { id: number }) {
  const uid = useId();
  const linksHeadingId = useId();
  const [detail, setDetail] = useState<GameRequestDetail | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [form, setForm] = useState<RequestForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>([]);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [reveals, setReveals] = useState<{ name: string; reveal: TokenReveal }[]>([]);

  const initial = useMemo(() => (detail ? toForm(detail) : null), [detail]);
  const dirty = form !== null && initial !== null && JSON.stringify(form) !== JSON.stringify(initial);
  const readOnly = detail !== null && detail.status !== "pending";

  const show = (next: GameRequestDetail) => {
    setDetail(next);
    setForm(toForm(next));
  };

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setLoadError("Request not found.");
      setLoading(false);
      return;
    }
    Promise.all([adminApi.gameRequest(id), adminApi.games()])
      .then(([request, allGames]) => {
        if (cancelled) return;
        setGames(allGames);
        show(request);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof HttpErrorWithBody && err.status === 404
            ? "Request not found."
            : "Could not load the request.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const clearMessages = () => {
    setError(null);
    setNotice(null);
    setServerError(null);
    setFieldErrors([]);
  };

  /** 409: someone else changed or decided the request; show the current state instead. */
  const reloadAfterConflict = async () => {
    try {
      const fresh = await adminApi.gameRequest(id);
      show(fresh);
      if (fresh.status === "pending") {
        setNotice("Another admin changed this request. It has been reloaded; check it and try again.");
      } else {
        setNotice(`Another admin has already ${fresh.status} this request. It is now read-only.`);
        window.dispatchEvent(new Event(REQUESTS_CHANGED));
      }
    } catch {
      setError("Another admin changed this request. Please refresh the page.");
    }
  };

  const handleError = async (err: unknown, fallback: string) => {
    if (isValidationError(err)) {
      setFieldErrors(
        (err.body as AdminValidationError).errors.map((e) => ({
          field: normalizeField(e.field),
          message: e.message,
        })),
      );
    } else if (isConflictError(err)) {
      await reloadAfterConflict();
    } else if (isServerError(err)) {
      setServerError(getServerReference(err) ?? "Server error");
    } else {
      setError(fallback);
    }
  };

  const handleSave = async () => {
    if (!detail || !form) return;
    clearMessages();
    if (!form.game_id) {
      setFieldErrors([{ field: "game_id", message: "Choose a game" }]);
      return;
    }
    setBusy(true);
    try {
      show(await adminApi.updateGameRequest(detail.id, toUpdate(form, detail)));
      setNotice("Changes saved.");
    } catch (err) {
      await handleError(err, "Could not save the request.");
    } finally {
      setBusy(false);
    }
  };

  const handleApprove = async () => {
    if (!detail) return;
    clearMessages();
    setBusy(true);
    try {
      const tokens = await adminApi.approveGameRequest(detail.id, detail.updated_at);
      setReveals(
        tokens.map((reveal, i) => ({ name: detail.teams[i]?.name ?? `Team ${i + 1}`, reveal })),
      );
      window.dispatchEvent(new Event(REQUESTS_CHANGED));
      try {
        show(await adminApi.gameRequest(detail.id));
      } catch {
        show({ ...detail, status: "approved" });
      }
    } catch (err) {
      await handleError(err, "Could not approve the request.");
    } finally {
      setConfirm(null);
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!detail) return;
    clearMessages();
    setBusy(true);
    try {
      show(await adminApi.rejectGameRequest(detail.id, detail.updated_at));
      window.dispatchEvent(new Event(REQUESTS_CHANGED));
    } catch (err) {
      await handleError(err, "Could not reject the request.");
    } finally {
      setConfirm(null);
      setBusy(false);
    }
  };

  const updateForm = (patch: Partial<RequestForm>) => {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));
  };

  const updateTeam = (index: number, patch: Partial<TeamRow>) => {
    setForm((prev) =>
      prev
        ? { ...prev, teams: prev.teams.map((t, i) => (i === index ? { ...t, ...patch } : t)) }
        : prev,
    );
  };

  const addTeam = () => {
    setForm((prev) =>
      prev
        ? {
            ...prev,
            teams: [
              ...prev.teams,
              { name: "", key: "", participants: "", valid_from: "", valid_until: "", team_id: null },
            ],
          }
        : prev,
    );
  };

  const removeTeam = (index: number) => {
    setForm((prev) => (prev ? { ...prev, teams: prev.teams.filter((_, i) => i !== index) } : prev));
    setFieldErrors((prev) => prev.filter((e) => !e.field.startsWith("teams.")));
  };

  const errorsFor = (field: string) => fieldErrors.filter((e) => e.field === field);

  if (loading || loadError || !detail || !form) {
    return (
      <div className="admin-section">
        <h1 className="t-title">Request</h1>
        {loading ? (
          <p className="t-body">Loading…</p>
        ) : (
          <p className="qc-field__error">{loadError ?? "Could not load the request."}</p>
        )}
        <div className="admin-actions">
          <a className="qc-btn qc-btn--secondary" href="/admin/requests">
            Back to requests
          </a>
        </div>
      </div>
    );
  }

  const selectedGame = games.find((g) => String(g.id) === form.game_id);
  const timeZone = selectedGame?.time_zone ?? detail.game_time_zone;
  const gameName = selectedGame?.name ?? detail.game_name ?? "the game";
  const input = (field: string) => ({
    id: `${uid}-${field}`,
    "aria-invalid": errorsFor(field).length ? ("true" as const) : undefined,
    "aria-describedby": errorsFor(field).length ? `${uid}-${field}-error` : undefined,
    disabled: readOnly || busy,
  });

  return (
    <div className="admin-section">
      <h1 className="t-title">Request from {detail.contact_name}</h1>
      {notice && (
        <p className="t-body" role="status">
          {notice}
        </p>
      )}
      {error && <p className="qc-field__error">{error}</p>}
      {serverError && <p className="qc-field__error">Server reference: {serverError}</p>}
      <FieldErrorList errors={fieldErrors.filter((e) => !INLINE_FIELD.test(e.field))} />

      {reveals.length > 0 && (
        <section className="admin-group" aria-labelledby={linksHeadingId}>
          <h2 className="t-subtitle" id={linksHeadingId}>
            Play links
          </h2>
          <p className="t-body">
            Copy these links now and share them with the teams. They are shown only once; reissue a
            token on the Teams screen for a new link.
          </p>
          <ul className="admin-list">
            {reveals.map(({ name, reveal }) => (
              <li key={reveal.assignment_id} className="admin-list-item">
                <strong className="t-body">{name}</strong>
                <TokenLink reveal={reveal} busy={busy} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="admin-card">
        <dl className="admin-facts">
          <dt>Status</dt>
          <dd>
            {STATUS_LABEL[detail.status]}
            {detail.decided_by && ` by ${detail.decided_by}`}
            {detail.decided_at && ` on ${formatTime(detail.decided_at)}`}
          </dd>
          <dt>Received</dt>
          <dd>{formatTime(detail.created_at)}</dd>
          <dt>Contact</dt>
          <dd>{detail.contact_name}</dd>
          {detail.contact_email && (
            <>
              <dt>Email</dt>
              <dd>
                <a href={`mailto:${detail.contact_email}`}>{detail.contact_email}</a>
              </dd>
            </>
          )}
          {detail.contact_phone && (
            <>
              <dt>Phone</dt>
              <dd>{detail.contact_phone}</dd>
            </>
          )}
          <dt>Play date</dt>
          <dd>{detail.play_date}</dd>
          {detail.message && (
            <>
              <dt>Message</dt>
              <dd>{detail.message}</dd>
            </>
          )}
          <dt>Terms accepted</dt>
          <dd>{`${formatTime(detail.terms_accepted_at)}, version ${detail.terms_version}`}</dd>
        </dl>
      </div>

      <div className="admin-form">
        <Field id={`${uid}-game_id`} label="Game" errors={errorsFor("game_id")}>
          <select
            className="qc-input"
            value={form.game_id}
            onChange={(e) => updateForm({ game_id: e.target.value })}
            {...input("game_id")}
          >
            {!selectedGame && <option value="">Choose a game</option>}
            {games.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </Field>
        <Field id={`${uid}-exit_message`} label="Exit message" errors={errorsFor("exit_message")}>
          <textarea
            className="qc-input"
            rows={2}
            value={form.exit_message}
            onChange={(e) => updateForm({ exit_message: e.target.value })}
            {...input("exit_message")}
          />
        </Field>

        <h2 className="t-subtitle">Teams</h2>
        <p className="t-caption">
          Times are in {timeZone ?? "the game's time zone"}. A team left at the whole play date
          ({DEFAULT_FROM.slice(0, 5)} to {DEFAULT_UNTIL}) keeps the play-date default.
        </p>
        <div className="admin-assignments">
          {form.teams.map((team, index) => {
            const field = (name: keyof TeamRow) => `teams.${index}.${name}`;
            return (
              <fieldset key={index} className="admin-assignment">
                <legend className="t-body">Team {index + 1}</legend>
                <Field id={`${uid}-${field("name")}`} label="Name" errors={errorsFor(field("name"))}>
                  <input
                    className="qc-input"
                    type="text"
                    value={team.name}
                    onChange={(e) => updateTeam(index, { name: e.target.value })}
                    {...input(field("name"))}
                  />
                </Field>
                <Field id={`${uid}-${field("key")}`} label="Key" errors={errorsFor(field("key"))}>
                  <input
                    className="qc-input"
                    type="text"
                    value={team.key}
                    onChange={(e) => updateTeam(index, { key: e.target.value })}
                    {...input(field("key"))}
                  />
                </Field>
                <Field
                  id={`${uid}-${field("participants")}`}
                  label="Participants"
                  errors={errorsFor(field("participants"))}
                >
                  <input
                    className="qc-input"
                    type="number"
                    min={1}
                    value={team.participants}
                    onChange={(e) => updateTeam(index, { participants: e.target.value })}
                    {...input(field("participants"))}
                  />
                </Field>
                <Field
                  id={`${uid}-${field("valid_from")}`}
                  label="Valid from"
                  errors={errorsFor(field("valid_from"))}
                >
                  <input
                    className="qc-input"
                    type="datetime-local"
                    step={1}
                    value={team.valid_from}
                    onChange={(e) => updateTeam(index, { valid_from: e.target.value })}
                    {...input(field("valid_from"))}
                  />
                </Field>
                <Field
                  id={`${uid}-${field("valid_until")}`}
                  label="Valid until"
                  errors={errorsFor(field("valid_until"))}
                >
                  <input
                    className="qc-input"
                    type="datetime-local"
                    step={1}
                    value={team.valid_until}
                    onChange={(e) => updateTeam(index, { valid_until: e.target.value })}
                    {...input(field("valid_until"))}
                  />
                </Field>
                {readOnly && team.team_id !== null && (
                  <div className="admin-row-actions">
                    <a className="qc-btn qc-btn--secondary" href={`/admin/teams/${team.team_id}`}>
                      Open team
                    </a>
                  </div>
                )}
                {!readOnly && (
                  <div className="admin-row-actions">
                    <button
                      type="button"
                      className="qc-btn qc-btn--danger"
                      onClick={() => removeTeam(index)}
                      disabled={busy || form.teams.length === 1}
                    >
                      Remove
                    </button>
                  </div>
                )}
              </fieldset>
            );
          })}
        </div>
        {!readOnly && (
          <div className="admin-actions">
            <button type="button" className="qc-btn qc-btn--secondary" onClick={addTeam} disabled={busy}>
              Add team
            </button>
            <button
              type="button"
              className="qc-btn qc-btn--primary"
              onClick={handleSave}
              disabled={!dirty || busy}
            >
              Save changes
            </button>
            {dirty && (
              <button
                type="button"
                className="qc-btn qc-btn--secondary"
                onClick={() => {
                  if (initial) setForm(initial);
                  setFieldErrors([]);
                }}
                disabled={busy}
              >
                Discard changes
              </button>
            )}
          </div>
        )}
      </div>

      <div className="admin-actions">
        {!readOnly && (
          <>
            <button
              type="button"
              className="qc-btn qc-btn--primary"
              onClick={() => setConfirm("approve")}
              disabled={dirty || busy}
            >
              Approve
            </button>
            <button
              type="button"
              className="qc-btn qc-btn--danger"
              onClick={() => setConfirm("reject")}
              disabled={dirty || busy}
            >
              Reject
            </button>
          </>
        )}
        <a className="qc-btn qc-btn--secondary" href="/admin/requests">
          Back to requests
        </a>
      </div>
      {!readOnly && dirty && (
        <p className="t-caption">Save or discard your changes before deciding.</p>
      )}

      {confirm === "approve" && (
        <ConfirmDialog
          title="Approve request"
          body={`This creates ${teamsLabel(detail.teams.length)}, assigns them to ${gameName} and issues their play links. It cannot be undone.`}
          confirmLabel="Approve"
          busy={busy}
          onConfirm={handleApprove}
          onCancel={() => setConfirm(null)}
        />
      )}
      {confirm === "reject" && (
        <ConfirmDialog
          title="Reject request"
          body="The request is marked rejected and nothing is created. It cannot be undone."
          confirmLabel="Reject"
          danger
          busy={busy}
          onConfirm={handleReject}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
