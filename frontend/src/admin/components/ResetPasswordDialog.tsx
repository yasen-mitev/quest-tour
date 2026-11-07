import { useEffect, useId, useRef, useState } from "react";

interface ResetPasswordDialogProps {
  email: string;
  minLength: number;
  busy?: boolean;
  /** The server's refusal, shown inside the dialog so the admin can correct and retry. */
  error?: string | null;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}

/** Sets a new password for another administrator. Same sheet as ConfirmDialog, but a form:
 *  focus starts in the first field, Enter submits, Escape and the scrim cancel. */
export function ResetPasswordDialog({
  email,
  minLength,
  busy = false,
  error = null,
  onSubmit,
  onCancel,
}: ResetPasswordDialogProps) {
  const titleId = useId();
  const firstRef = useRef<HTMLInputElement>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);

  useEffect(() => { firstRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== repeat) return setInvalid("The new passwords do not match.");
    if (password.length < minLength) {
      return setInvalid(`The new password must be at least ${minLength} characters.`);
    }
    setInvalid(null);
    onSubmit(password);
  };

  const message = invalid ?? error;

  return (
    <div className="qs-overlay qc-scrim" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <form className="qc-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} onSubmit={submit}>
        <h2 className="qc-sheet__title" id={titleId}>Reset password for {email}</h2>
        <p className="qc-sheet__body">
          The new password takes effect immediately. Give it to {email} yourself; they are not notified.
        </p>
        <label className="qc-field">
          <span className="qc-field__label">New password</span>
          <input ref={firstRef} className="qc-input" type="password" value={password} required
                 autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="qc-field">
          <span className="qc-field__label">Repeat new password</span>
          <input className="qc-input" type="password" value={repeat} required
                 autoComplete="new-password" onChange={(e) => setRepeat(e.target.value)} />
        </label>
        {message && <p className="qc-field__error" role="alert">{message}</p>}
        <div className="qc-sheet__actions">
          <button type="submit" disabled={busy} className="qc-btn qc-btn--primary qc-btn--block">
            Reset password
          </button>
          <button type="button" className="qc-btn qc-btn--secondary qc-btn--block" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
