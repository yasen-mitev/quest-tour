import { useCallback, useEffect, useState } from "react";
import { adminApi, HttpErrorWithBody, type AdminUserOut, type AuthSettings } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AddAdminDialog } from "../components/AddAdminDialog";
import { PasswordField } from "../components/PasswordField";
import { ResetPasswordDialog } from "../components/ResetPasswordDialog";
import { Icon } from "../../components/Icon";

const MIN_PASSWORD_LENGTH = 12;
const SELF_REMOVE_REASON = "You cannot remove yourself";

/** The message to show for a failed settings call: the server's own reason for a 409, its first
 *  validation message for a 422, otherwise the screen's fallback. */
function failureMessage(err: unknown, fallback: string): string {
  if (err instanceof HttpErrorWithBody) {
    if (err.status === 409) {
      const detail = (err.body as { detail?: string } | null)?.detail;
      if (detail) return detail;
    }
    if (err.status === 422) {
      const message = (err.body as { errors?: { message: string }[] } | null)?.errors?.[0]?.message;
      if (message) return message;
    }
  }
  return fallback;
}

/** Everything about the administrators of this panel (issue: password admins by default): for admins
 *  signed in with a password, the list of password administrators and their own password; for
 *  everyone, how administrators may sign in (the Microsoft Entra toggle). */
export function AdministratorsScreen() {
  const [settings, setSettings] = useState<AuthSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.authSettings().then(setSettings).catch(() => setError("Could not load the sign-in settings."));
  }, []);

  return (
    <div className="admin-section admin-section--narrow">
      <h1 className="t-title">Administrators</h1>
      {error && <p className="qc-field__error">{error}</p>}
      {!settings && !error && <p className="t-body">Loading…</p>}
      {settings && (
        <>
          {settings.session_provider === "password" ? (
            <>
              <AdministratorsSection me={settings.email} />
              <ChangePasswordSection />
            </>
          ) : (
            <p className="t-body">Password admins are managed by a password admin.</p>
          )}
          <EntraSection settings={settings} />
        </>
      )}
    </div>
  );
}

function EntraSection({ settings }: { settings: AuthSettings }) {
  const [enabled, setEnabled] = useState(settings.entra_enabled);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = !settings.entra_configured || settings.mode === "dev";

  const toggle = async (next: boolean) => {
    setError(null);
    setBusy(true);
    try {
      const res = await adminApi.setEntraEnabled(next);
      setEnabled(res.entra_enabled);
    } catch (err) {
      setError(failureMessage(err, "Could not change the sign-in setting."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="admin-group" aria-labelledby="admins-signin">
      <h2 className="t-subtitle" id="admins-signin">Sign-in methods</h2>
      <div className="admin-form">
        <label className="admin-check">
          <input
            type="checkbox"
            checked={enabled}
            disabled={locked || busy}
            onChange={(e) => toggle(e.target.checked)}
          />
          Microsoft Entra sign-in
        </label>
        {!settings.entra_configured && (
          <p className="t-caption">Microsoft sign-in isn't set up on this server yet.</p>
        )}
        {settings.mode === "dev" && (
          <p className="t-caption">Sign-in is fixed to development mode on this server.</p>
        )}
        {error && <p className="qc-field__error">{error}</p>}
      </div>
    </section>
  );
}

function ChangePasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (next !== repeat) return setError("The new passwords do not match.");
    if (next.length < MIN_PASSWORD_LENGTH) {
      return setError(`The new password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
    }
    try {
      await adminApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setRepeat("");
      setDone(true);
    } catch (err) {
      setError(
        err instanceof HttpErrorWithBody && err.status === 400
          ? "Current password is wrong"
          : failureMessage(err, "Could not change the password."),
      );
    }
  };

  return (
    <section className="admin-group" aria-labelledby="admins-password">
      <h2 className="t-subtitle" id="admins-password">Change my password</h2>
      <form onSubmit={submit} className="admin-form">
        <PasswordField label="Current password" value={current} onChange={setCurrent}
                       autoComplete="current-password" />
        <PasswordField label="New password" value={next} onChange={setNext} autoComplete="new-password"
                       minLength={MIN_PASSWORD_LENGTH} />
        <PasswordField label="Repeat new password" value={repeat} onChange={setRepeat} autoComplete="new-password"
                       matches={next} />
        <button className="qc-btn qc-btn--primary" type="submit">Change password</button>
        {error && <p className="qc-field__error">{error}</p>}
        {done && (
          <p className="admin-success" role="status">
            <Icon name="check" />
            Your password was changed. Other devices where you're signed in stay signed in.
          </p>
        )}
      </form>
    </section>
  );
}

/** The line under an admin's email: "First administrator", "You", both, or nothing. */
function rowCaption(admin: AdminUserOut, me: string): string {
  return [admin.is_bootstrap && "First administrator", admin.email === me && "You"]
    .filter(Boolean)
    .join(" · ");
}

function AdministratorsSection({ me }: { me: string }) {
  const [admins, setAdmins] = useState<AdminUserOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A confirmation on the row just added or changed; it stays until the next action here.
  const [rowNotice, setRowNotice] = useState<{ id: number; text: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<AdminUserOut | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<AdminUserOut | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setAdmins(await adminApi.listAdmins());
    } catch {
      setError("Could not load the administrators.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openAdd = () => {
    setError(null);
    setRowNotice(null);
    setAddError(null);
    setAdding(true);
  };

  // Failures stay in the dialog, so the admin can correct the entry and retry.
  const add = async (email: string, password: string) => {
    setAddError(null);
    setBusy(true);
    try {
      const created = await adminApi.createAdmin(email, password);
      setAdding(false);
      setRowNotice({ id: created.id, text: "Added. They aren't notified, so give them the password yourself." });
      await load();
    } catch (err) {
      setAddError(failureMessage(err, "Could not add the administrator."));
    } finally {
      setBusy(false);
    }
  };

  const openRemove = (admin: AdminUserOut) => {
    setError(null);
    setRowNotice(null);
    setRemoving(admin);
  };

  const remove = async () => {
    if (!removing) return;
    setError(null);
    setRowNotice(null);
    setBusy(true);
    try {
      await adminApi.deleteAdmin(removing.id);
      await load();
    } catch (err) {
      setError(failureMessage(err, "Could not remove the administrator."));
    } finally {
      setBusy(false);
      setRemoving(null);
    }
  };

  const openReset = (admin: AdminUserOut) => {
    setError(null);
    setRowNotice(null);
    setResetError(null);
    setResetting(admin);
  };

  // Failures stay in the dialog, so the admin can correct the password and retry.
  const reset = async (password: string) => {
    if (!resetting) return;
    setResetError(null);
    setBusy(true);
    try {
      await adminApi.resetAdminPassword(resetting.id, password);
      setRowNotice({
        id: resetting.id,
        text: resetting.email === me
          ? "New password set. Use it the next time you sign in."
          : "New password set. They aren't notified, so give it to them yourself.",
      });
      setResetting(null);
    } catch (err) {
      setResetError(failureMessage(err, "Could not reset the password."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="admin-group" aria-labelledby="admins-list">
      <h2 className="t-subtitle" id="admins-list">All administrators</h2>
      {error && <p className="qc-field__error">{error}</p>}
      {/* One card like the other sections: the admins as divided rows, the add button at the foot. */}
      <div className="admin-card">
        {admins && (
          <ul className="admin-list admin-list--in-card" aria-labelledby="admins-list">
            {admins.map((admin) => (
              <li key={admin.id} className="admin-list-item">
                <div>
                  <strong className="t-body">{admin.email}</strong>
                  {rowCaption(admin, me) && <p className="t-caption">{rowCaption(admin, me)}</p>}
                  {rowNotice?.id === admin.id && (
                    <p className="admin-success" role="status">
                      <Icon name="check" />
                      {rowNotice.text}
                    </p>
                  )}
                </div>
                <div className="admin-row-actions">
                  <button type="button" className="qc-btn qc-btn--secondary" onClick={() => openReset(admin)}>
                    Reset password
                  </button>
                  {/* The server refuses to remove the signed-in admin. The button stays (disabled) so the
                      button columns line up; the reason is a tooltip and the screen-reader description. */}
                  {admin.email === me ? (
                    <>
                      <button type="button" className="qc-btn qc-btn--secondary" disabled
                              title={SELF_REMOVE_REASON} aria-describedby={`admin-${admin.id}-no-remove`}>
                        Remove
                      </button>
                      <span id={`admin-${admin.id}-no-remove`} hidden>{SELF_REMOVE_REASON}</span>
                    </>
                  ) : (
                    <button type="button" className="qc-btn qc-btn--secondary" onClick={() => openRemove(admin)}>
                      Remove
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="admin-card__footer">
          <button type="button" className="qc-btn qc-btn--primary" onClick={openAdd}>
            Add administrator
          </button>
        </div>
      </div>
      {adding && (
        <AddAdminDialog
          minLength={MIN_PASSWORD_LENGTH}
          busy={busy}
          error={addError}
          onSubmit={add}
          onCancel={() => setAdding(false)}
        />
      )}
      {resetting && (
        <ResetPasswordDialog
          email={resetting.email}
          minLength={MIN_PASSWORD_LENGTH}
          busy={busy}
          error={resetError}
          onSubmit={reset}
          onCancel={() => setResetting(null)}
        />
      )}
      {removing && (
        <ConfirmDialog
          title="Remove administrator"
          body={`${removing.email} will no longer be able to sign in.`}
          confirmLabel="Remove"
          danger
          busy={busy}
          onConfirm={remove}
          onCancel={() => setRemoving(null)}
        />
      )}
    </section>
  );
}
