import { useEffect, useMemo, useState } from "react";
import { adminApi, getServerReference, isConflictError, isServerError, isValidationError, normalizeField } from "../api";
import type { AdminValidationError } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EntityForm } from "../components/EntityForm";
import type { FieldDef } from "../components/EntityForm";
import { FieldErrorList } from "../components/FieldErrorList";
import type { Game, GameInput, Landmark } from "../types";

type GameForm = {
  key: string;
  name: string;
  intro: string;
  time_zone: string;
  max_duration_minutes: number;
  reveal_attempts: number;
  reveal_minutes: number;
  reveal_penalty_minutes: number;
  requestable: boolean;
};

const GAME_FIELDS: FieldDef[] = [
  { name: "key", label: "Key", type: "text" as const, required: true },
  { name: "name", label: "Name", type: "text" as const, required: true },
  { name: "intro", label: "Intro", type: "textarea" as const, required: true, rows: 5 },
  { name: "time_zone", label: "Time zone", type: "text" as const, required: true },
  { name: "max_duration_minutes", label: "Duration (minutes)", type: "number" as const, required: true },
  { name: "reveal_attempts", label: "Reveal attempts", type: "number" as const, required: true },
  { name: "reveal_minutes", label: "Reveal minutes", type: "number" as const, required: true },
  { name: "reveal_penalty_minutes", label: "Reveal penalty (minutes)", type: "number" as const, required: true },
  { name: "requestable", label: "Requestable on the website", type: "checkbox" as const },
];

function emptyForm(): GameForm {
  return {
    key: "",
    name: "",
    intro: "",
    time_zone: "UTC",
    max_duration_minutes: 60,
    reveal_attempts: 5,
    reveal_minutes: 20,
    reveal_penalty_minutes: 30,
    requestable: false,
  };
}

function gameToForm(game: Game): GameForm {
  return {
    key: game.key,
    name: game.name,
    intro: game.intro,
    time_zone: game.time_zone,
    max_duration_minutes: game.max_duration_minutes,
    reveal_attempts: game.reveal.attempts,
    reveal_minutes: game.reveal.minutes,
    reveal_penalty_minutes: game.reveal.penalty_minutes,
    requestable: game.requestable,
  };
}

function formToGame(form: GameForm): GameInput {
  return {
    key: form.key,
    name: form.name,
    intro: form.intro,
    time_zone: form.time_zone,
    max_duration_minutes: form.max_duration_minutes,
    reveal: {
      attempts: form.reveal_attempts,
      minutes: form.reveal_minutes,
      penalty_minutes: form.reveal_penalty_minutes,
    },
    requestable: form.requestable,
  };
}

export function GamesScreen({ subPath }: { subPath: string }) {
  const [games, setGames] = useState<Game[]>([]);
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Game | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<AdminValidationError["errors"]>([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [taskIds, setTaskIds] = useState<number[]>([]);
  const [tasksDirty, setTasksDirty] = useState(false);
  const [addTaskId, setAddTaskId] = useState<string>("");

  const load = () => {
    setLoading(true);
    return Promise.all([adminApi.games(), adminApi.landmarks()])
      .then(([g, l]) => {
        setGames(g);
        setLandmarks(l);
        return [g, l] as const;
      })
      .catch(() => {
        setError("Could not load games.");
        return [games, landmarks] as const;
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const segments = subPath.split("/").filter(Boolean);
    if (segments[0] !== "games") return;
    if (segments[1] === "new") {
      setCreating(true);
      setEditing(null);
    } else if (segments[1]) {
      const id = Number(segments[1]);
      if (!id) return;
      const target = games.find((g) => g.id === id);
      if (target) {
        setEditing(target);
        setCreating(false);
      }
    }
  }, [subPath, games]);

  useEffect(() => {
    if (!dirty && !tasksDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty, tasksDirty]);

  useEffect(() => {
    if (editing) {
      setTaskIds(editing.task_landmark_ids);
    } else {
      setTaskIds([]);
    }
    setTasksDirty(false);
    setAddTaskId("");
  }, [editing, creating]);

  const initial = useMemo(
    () => (editing ? gameToForm(editing) : emptyForm()),
    [editing, creating],
  );

  const handleSave = async (form: GameForm) => {
    setError(null);
    setFieldErrors([]);
    setServerError(null);

    const data = formToGame(form);
    setBusy(true);
    try {
      if (editing) {
        await adminApi.updateGame(editing.id, { ...data, seen_at: editing.updated_at });
      } else {
        await adminApi.createGame(data);
      }
      setEditing(null);
      setCreating(false);
      setDirty(false);
      load();
    } catch (err) {
      if (isValidationError(err)) {
        setFieldErrors((err.body as AdminValidationError).errors.map((e) => ({ field: normalizeField(e.field), message: e.message })));
      } else if (isConflictError(err)) {
        setError("Another admin edited this game. Please refresh.");
      } else if (isServerError(err)) {
        setServerError(getServerReference(err) ?? "Server error");
      } else {
        setError("Could not save game.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSaveTasks = async () => {
    if (!editing) return;
    setError(null);
    setServerError(null);
    setBusy(true);
    try {
      await adminApi.updateGameTasks(editing.id, taskIds, editing.updated_at);
      setTasksDirty(false);
      const [updatedGames] = await load();
      if (editing) {
        const next = updatedGames.find((g) => g.id === editing.id);
        if (next) setEditing(next);
      }
    } catch (err) {
      if (isValidationError(err)) {
        setFieldErrors((err.body as AdminValidationError).errors.map((e) => ({ field: normalizeField(e.field), message: e.message })));
      } else if (isConflictError(err)) {
        setError("Another admin edited this game. Please refresh.");
      } else if (isServerError(err)) {
        setServerError(getServerReference(err) ?? "Server error");
      } else {
        setError("Could not save tasks.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id: number) => {
    setBusy(true);
    try {
      await adminApi.deleteGame(id);
      setDeleteId(null);
      load();
    } catch {
      setError("Could not delete game.");
    } finally {
      setBusy(false);
    }
  };

  const moveTask = (index: number, direction: -1 | 1) => {
    setTaskIds((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setTasksDirty(true);
  };

  const removeTask = (id: number) => {
    setTaskIds((prev) => prev.filter((tid) => tid !== id));
    setTasksDirty(true);
  };

  const addTask = () => {
    const id = Number(addTaskId);
    if (!id || taskIds.includes(id)) return;
    setTaskIds((prev) => [...prev, id]);
    setAddTaskId("");
    setTasksDirty(true);
  };

  const selectedTasks = taskIds
    .map((id) => landmarks.find((lm) => lm.id === id))
    .filter(Boolean) as Landmark[];

  const availableTasks = landmarks.filter((lm) => !taskIds.includes(lm.id));

  if (loading) {
    return (
      <div className="admin-section">
        <h1 className="t-title">Games</h1>
        <p className="t-body">Loading…</p>
      </div>
    );
  }

  if (creating || editing) {
    return (
      <div className="admin-section">
        <h1 className="t-title">{editing ? "Edit game" : "New game"}</h1>
        {error && <p className="qc-field__error">{error}</p>}
        {serverError && <p className="qc-field__error">Server reference: {serverError}</p>}
        <FieldErrorList errors={fieldErrors} />
        <EntityForm
          fields={GAME_FIELDS}
          initial={initial}
          onSubmit={handleSave}
          onDirtyChange={setDirty}
          errors={fieldErrors}
          submitLabel={editing ? "Update game" : "Create game"}
          busy={busy}
        />
        {editing && (
          <div className="admin-extra-fields">
            <h2 className="t-subtitle">Tasks</h2>
            {fieldErrors.some((e) => e.field === "landmark_ids") && (
              <p className="qc-field__error">
                {fieldErrors.find((e) => e.field === "landmark_ids")?.message}
              </p>
            )}
            {selectedTasks.length === 0 ? (
              <p className="t-body">No tasks yet.</p>
            ) : (
              <ul className="admin-list">
                {selectedTasks.map((lm, index) => (
                  <li key={lm.id} className="admin-list-item">
                    <span className="t-body">{lm.name}</span>
                    <div className="admin-row-actions">
                      <button
                        type="button"
                        className="qc-btn qc-btn--secondary"
                        onClick={() => moveTask(index, -1)}
                        disabled={index === 0 || busy}
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        className="qc-btn qc-btn--secondary"
                        onClick={() => moveTask(index, 1)}
                        disabled={index === selectedTasks.length - 1 || busy}
                      >
                        Down
                      </button>
                      <button
                        type="button"
                        className="qc-btn qc-btn--danger"
                        onClick={() => removeTask(lm.id)}
                        disabled={busy}
                        aria-label={`Remove ${lm.name}`}
                      >
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="admin-row-actions">
              <label className="qc-field">
                <span className="qc-field__label">Add landmark</span>
                <select
                  className="qc-input"
                  value={addTaskId}
                  onChange={(e) => setAddTaskId(e.target.value)}
                  disabled={busy}
                  aria-label="Add landmark"
                >
                  <option value="">Choose a landmark</option>
                  {availableTasks.map((lm) => (
                    <option key={lm.id} value={lm.id}>
                      {lm.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="qc-btn qc-btn--secondary"
                onClick={addTask}
                disabled={!addTaskId || busy}
              >
                Add landmark
              </button>
            </div>
            <button
              type="button"
              className="qc-btn qc-btn--primary"
              onClick={handleSaveTasks}
              disabled={!tasksDirty || busy}
            >
              Save tasks
            </button>
          </div>
        )}
        <div className="admin-actions">
          <button
            className="qc-btn qc-btn--secondary"
            type="button"
            onClick={() => {
              if ((dirty || tasksDirty) && !window.confirm("Discard unsaved changes?")) return;
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
      <h1 className="t-title">Games</h1>
      {error && <p className="qc-field__error">{error}</p>}
      <div className="admin-actions">
        <button className="qc-btn qc-btn--primary" type="button" onClick={() => setCreating(true)}>
          New game
        </button>
      </div>
      {games.length === 0 ? (
        <p className="t-body">No games yet.</p>
      ) : (
        <ul className="admin-list">
          {games.map((g) => (
            <li key={g.id} className="admin-list-item">
              <div>
                <strong className="t-body">{g.name}</strong>
                <span className="t-caption"> ({g.key})</span>
              </div>
              <div className="admin-row-actions">
                <button
                  className="qc-btn qc-btn--secondary"
                  type="button"
                  onClick={() => setEditing(g)}
                >
                  Edit
                </button>
                <button
                  className="qc-btn qc-btn--danger"
                  type="button"
                  onClick={() => setDeleteId(g.id)}
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
          title="Delete game"
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
