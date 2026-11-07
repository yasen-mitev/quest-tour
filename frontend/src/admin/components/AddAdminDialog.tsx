import { useEffect, useRef, useState } from "react";
import { PasswordField } from "./PasswordField";
import { SheetForm } from "./SheetForm";

interface AddAdminDialogProps {
  minLength: number;
  busy?: boolean;
  /** The server's refusal (e.g. the e-mail exists), shown inside the dialog so the admin can retry. */
  error?: string | null;
  onSubmit: (email: string, password: string) => void;
  onCancel: () => void;
}

/** Adds a password administrator. Focus starts in the e-mail field. */
export function AddAdminDialog({ minLength, busy = false, error = null, onSubmit, onCancel }: AddAdminDialogProps) {
  const emailRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);

  useEffect(() => { emailRef.current?.focus(); }, []);

  const submit = () => {
    if (password !== repeat) return setInvalid("The passwords do not match.");
    if (password.length < minLength) return setInvalid(`The password must be at least ${minLength} characters.`);
    setInvalid(null);
    onSubmit(email, password);
  };

  return (
    <SheetForm
      title="Add an administrator"
      note="They can sign in right away. Give them the password yourself; they are not notified."
      submitLabel="Add administrator"
      busy={busy}
      error={invalid ?? error}
      onSubmit={submit}
      onCancel={onCancel}
    >
      <label className="qc-field">
        <span className="qc-field__label">Email</span>
        <input ref={emailRef} className="qc-input" type="email" value={email} required
               autoComplete="off" onChange={(e) => setEmail(e.target.value)} />
      </label>
      <PasswordField label="Password" value={password} onChange={setPassword}
                     autoComplete="new-password" minLength={minLength} />
      <PasswordField label="Repeat password" value={repeat} onChange={setRepeat}
                     autoComplete="new-password" matches={password} />
    </SheetForm>
  );
}
