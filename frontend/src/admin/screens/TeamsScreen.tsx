import { useEffect, useMemo, useRef, useState } from "react";
import { adminApi, getServerReference, isConflictError, isServerError, isValidationError, normalizeField } from "../api";
import type { AdminValidationError } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EntityForm } from "../components/EntityForm";
import type { FieldDef } from "../components/EntityForm";
import { FieldErrorList } from "../components/FieldErrorList";
import { TokenLink } from "../components/TokenLink";
import type { AssignmentCreate, AssignmentOut, Game, Team, TeamInput, TokenReveal } from "../types";

type TeamForm = {
  key: string;
  name: string;
  participants: string;
};

type AssignmentForm = AssignmentCreate & {
  id?: number;
  token_issued?: boolean;
  issued_at?: string | null;
};

const TEAM_FIELDS: FieldDef[] = [
  { name: "key", label: "Key", type: "text" as const, required: true },
  { name: "name", label: "Name", type: "text" as const, required: true },
  { name: "participants", label: "Participants", type: "text" as const },
];

function emptyForm(): TeamForm {
  return { key: "", name: "", participants: "" };
}

function teamToForm(team: Team): TeamForm {
  return {
    key: team.key,
    name: team.name,
    participants: team.participants === null ? "" : String(team.participants),
  };
}

function formToTeam(form: TeamForm): TeamInput {
  return {
    key: form.key,
    name: form.name,
    participants: form.participants.trim() === "" ? null : Number(form.participants),
  };
}

function toDateTimeLocal(value: string): string {
  return value.slice(0, 16);
}

export function TeamsScreen({ subPath }: { subPath: string }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Team | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<AdminValidationError["errors"]>([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [assignments, setAssignments] = useState<AssignmentForm[]>([]);
  const [assignmentsDirty, setAssignmentsDirty] = useState(false);
  const [revealedTokens, setRevealedTokens] = useState<Record<number, TokenReveal>>({});
  const previousEditingId = useRef<number | null>(null);

  const load = () => {
    setLoading(true);
    return Promise.all([adminApi.teams(), adminApi.games()])
      .then(([t, g]) => {
        setTeams(t);
        setGames(g);
        return [t, g] as const;
      })
      .catch(() => {
        setError("Could not load teams.");
        return [teams, games] as const;
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const segments = subPath.split("/").filter(Boolean);
    if (segments[0] !== "teams") return;
    if (segments[1] === "new") {
      setCreating(true);
      setEditing(null);
    } else if (segments[1]) {
      const id = Number(segments[1]);
      if (!id) return;
      const target = teams.find((t) => t.id === id);
      if (target) {
        setEditing(target);
        setCreating(false);
      }
    }
  }, [subPath, teams]);

  useEffect(() => {
    if (!dirty && !assignmentsDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty, assignmentsDirty]);

  useEffect(() => {
    const currentId = editing?.id ?? null;
    if (editing) {
      adminApi
        .teamAssignments(editing.id)
        .then((rows) => {
          setAssignments(
            rows.map((a) => ({
              game_id: a.game_id,
              valid_from: toDateTimeLocal(a.valid_from),
              valid_until: toDateTimeLocal(a.valid_until),
              exit_message: a.exit_message,
              id: a.id,
              token_issued: a.token_issued,
              issued_at: a.issued_at,
            })),
          );
        })
        .catch(() => setError("Could not load assignments."));
    } else {
      setAssignments([]);
    }
    setAssignmentsDirty(false);
    if (currentId !== previousEditingId.current) {
      setRevealedTokens({});
    }
    previousEditingId.current = currentId;
  }, [editing, creating]);

  const initial = useMemo(
    () => (editing ? teamToForm(editing) : emptyForm()),
    [editing, creating],
  );

  const handleSave = async (form: TeamForm) => {
    setError(null);
    setFieldErrors([]);
    setServerError(null);

    const data = formToTeam(form);
    setBusy(true);
    try {
      if (editing) {
        await adminApi.updateTeam(editing.id, { ...data, seen_at: editing.updated_at });
      } else {
        await adminApi.createTeam(data);
      }
      setEditing(null);
      setCreating(false);
      setDirty(false);
      load();
    } catch (err) {
      if (isValidationError(err)) {
        setFieldErrors(
          (err.body as AdminValidationError).errors.map((e) => ({
            field: normalizeField(e.field),
            message: e.message,
          }))
        );
      } else if (isConflictError(err)) {
        setError("Another admin edited this team. Please refresh.");
      } else if (isServerError(err)) {
        setServerError(getServerReference(err) ?? "Server error");
      } else {
        setError("Could not save team.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSaveAssignments = async () => {
    if (!editing) return;
    setError(null);
    setServerError(null);
    setBusy(true);
    const data: AssignmentCreate[] = assignments.map((a) => ({
      game_id: a.game_id,
      valid_from: a.valid_from,
      valid_until: a.valid_until,
      exit_message: a.exit_message,
    }));
    try {
      const tokens = await adminApi.updateTeamAssignments(editing.id, data, editing.updated_at);
      setAssignmentsDirty(false);
      setRevealedTokens(Object.fromEntries(tokens.map((t) => [t.assignment_id, t])));
      const [updatedTeams] = await load();
      if (editing) {
        const next = updatedTeams.find((t) => t.id === editing.id);
        if (next) setEditing(next);
      }
    } catch (err) {
      if (isValidationError(err)) {
        setFieldErrors(
          (err.body as AdminValidationError).errors.map((e) => ({
            field: normalizeField(e.field),
            message: e.message,
          }))
        );
      } else if (isConflictError(err)) {
        setError("Another admin edited this team. Please refresh.");
      } else if (isServerError(err)) {
        setServerError(getServerReference(err) ?? "Server error");
      } else {
        setError("Could not save assignments.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleReissue = async (assignmentId: number) => {
    setError(null);
    setServerError(null);
    try {
      const reveal = await adminApi.reissueToken(assignmentId);
      setRevealedTokens((prev) => ({ ...prev, [assignmentId]: reveal }));
    } catch {
      setError("Could not reissue token.");
    }
  };

  const handleDelete = async (id: number) => {
    setBusy(true);
    try {
      await adminApi.deleteTeam(id);
      setDeleteId(null);
      load();
    } catch {
      setError("Could not delete team.");
    } finally {
      setBusy(false);
    }
  };

  const updateAssignment = (index: number, patch: Partial<AssignmentForm>) => {
    setAssignments((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...patch };
      return next;
    });
    setAssignmentsDirty(true);
  };

  const removeAssignment = (index: number) => {
    setAssignments((prev) => prev.filter((_, i) => i !== index));
    setAssignmentsDirty(true);
  };

  const addAssignment = () => {
    const gameId = games[0]?.id ?? 0;
    setAssignments((prev) => [
      ...prev,
      { game_id: gameId, valid_from: "", valid_until: "", exit_message: "" },
    ]);
    setAssignmentsDirty(true);
  };

  if (loading) {
    return (
      <div className="admin-section">
        <h1 className="t-title">Teams</h1>
        <p className="t-body">Loading…</p>
      </div>
    );
  }

  if (creating || editing) {
    return (
      <div className="admin-section">
        <h1 className="t-title">{editing ? "Edit team" : "New team"}</h1>
        {error && <p className="qc-field__error">{error}</p>}
        {serverError && <p className="qc-field__error">Server reference: {serverError}</p>}
        <FieldErrorList errors={fieldErrors} />
        <EntityForm
          fields={TEAM_FIELDS}
          initial={initial}
          onSubmit={handleSave}
          onDirtyChange={setDirty}
          errors={fieldErrors}
          submitLabel={editing ? "Update team" : "Create team"}
          busy={busy}
        />
        {editing && (
          <div className="admin-extra-fields">
            <h2 className="t-subtitle">Assignments</h2>
            {assignments.length === 0 ? (
              <p className="t-body">No assignments yet.</p>
            ) : (
              <div className="admin-assignments">
                {assignments.map((a, index) => (
                  <fieldset key={index} className="admin-assignment">
                    <legend className="t-body">Assignment {index + 1}</legend>
                    <label className="qc-field">
                      <span className="qc-field__label">Game</span>
                      <select
                        className="qc-input"
                        value={a.game_id}
                        onChange={(e) => updateAssignment(index, { game_id: Number(e.target.value) })}
                        disabled={busy}
                        aria-label="Game"
                      >
                        {games.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="qc-field">
                      <span className="qc-field__label">Valid from</span>
                      <input
                        className="qc-input"
                        type="datetime-local"
                        value={a.valid_from}
                        onChange={(e) => updateAssignment(index, { valid_from: e.target.value })}
                        disabled={busy}
                        aria-label="Valid from"
                      />
                    </label>
                    <label className="qc-field">
                      <span className="qc-field__label">Valid until</span>
                      <input
                        className="qc-input"
                        type="datetime-local"
                        value={a.valid_until}
                        onChange={(e) => updateAssignment(index, { valid_until: e.target.value })}
                        disabled={busy}
                        aria-label="Valid until"
                      />
                    </label>
                    <label className="qc-field">
                      <span className="qc-field__label">Exit message</span>
                      <textarea
                        className="qc-input"
                        rows={2}
                        value={a.exit_message}
                        onChange={(e) => updateAssignment(index, { exit_message: e.target.value })}
                        disabled={busy}
                        aria-label="Exit message"
                      />
                    </label>
                    <div className="admin-row-actions">
                      {a.token_issued && (
                        <span className="t-caption">Token issued</span>
                      )}
                      {revealedTokens[a.id ?? -1] && (
                        <TokenLink reveal={revealedTokens[a.id ?? -1]} busy={busy} />
                      )}
                      <button
                        type="button"
                        className="qc-btn qc-btn--secondary"
                        onClick={() => handleReissue(a.id ?? 0)}
                        disabled={busy}
                      >
                        Reissue token
                      </button>
                      <button
                        type="button"
                        className="qc-btn qc-btn--danger"
                        onClick={() => removeAssignment(index)}
                        disabled={busy}
                      >
                        Remove
                      </button>
                    </div>
                  </fieldset>
                ))}
              </div>
            )}
            <div className="admin-actions">
              <button
                type="button"
                className="qc-btn qc-btn--secondary"
                onClick={addAssignment}
                disabled={busy}
              >
                Add assignment
              </button>
              <button
                type="button"
                className="qc-btn qc-btn--primary"
                onClick={handleSaveAssignments}
                disabled={!assignmentsDirty || busy}
              >
                Save assignments
              </button>
            </div>
          </div>
        )}
        <div className="admin-actions">
          <button
            className="qc-btn qc-btn--secondary"
            type="button"
            onClick={() => {
              if ((dirty || assignmentsDirty) && !window.confirm("Discard unsaved changes?")) return;
              setEditing(null);
              setCreating(false);
              setError(null);
              setFieldErrors([]);
              setServerError(null);
            }}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-section">
      <h1 className="t-title">Teams</h1>
      {error && <p className="qc-field__error">{error}</p>}
      <div className="admin-actions">
        <button className="qc-btn qc-btn--primary" type="button" onClick={() => setCreating(true)}>
          New team
        </button>
      </div>
      {teams.length === 0 ? (
        <p className="t-body">No teams yet.</p>
      ) : (
        <ul className="admin-list">
          {teams.map((t) => (
            <li key={t.id} className="admin-list-item">
              <div>
                <strong className="t-body">{t.name}</strong>
                <span className="t-caption"> ({t.key})</span>
              </div>
              <div className="admin-row-actions">
                <button
                  className="qc-btn qc-btn--secondary"
                  type="button"
                  onClick={() => setEditing(t)}
                >
                  Edit
                </button>
                <button
                  className="qc-btn qc-btn--danger"
                  type="button"
                  onClick={() => setDeleteId(t.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {deleteId !== null && (
        <ConfirmDialog
          title="Delete team"
          body="This cannot be undone."
          confirmLabel="Delete"
          danger
          busy={busy}
          onConfirm={() => handleDelete(deleteId)}
          onCancel={() => setDeleteId(null)}
        />
      )}
    </div>
  );
}
