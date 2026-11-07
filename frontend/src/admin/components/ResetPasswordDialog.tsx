import { useEffect, useRef, useState } from "react";
import { PasswordField } from "./PasswordField";
import { SheetForm } from "./SheetForm";

interface ResetPasswordDialogProps {
  email: string;
  minLength: number;
  busy?: boolean;
  /** The server's refusal, shown inside the dialog so the admin can correct and retry. */
  error?: string | null;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}

/** Sets a new password for another administrator. Focus starts in the first field. */
export function ResetPasswordDialog({
  email,
  minLength,
  busy = false,
  error = null,
  onSubmit,
  onCancel,
}: ResetPasswordDialogProps) {
  const firstRef = useRef<HTMLInputElement>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);

  useEffect(() => { firstRef.current?.focus(); }, []);

  const submit = () => {
    if (password !== repeat) return setInvalid("The new passwords do not match.");
    if (password.length < minLength) {
      return setInvalid(`The new password must be at least ${minLength} characters.`);
    }
    setInvalid(null);
    onSubmit(password);
  };

  return (
    <SheetForm
      title={`Reset password for ${email}`}
      note={`The new password takes effect immediately. Give it to ${email} yourself; they are not notified.`}
      submitLabel="Reset password"
      busy={busy}
      error={invalid ?? error}
      onSubmit={submit}
      onCancel={onCancel}
    >
      <PasswordField ref={firstRef} label="New password" value={password} onChange={setPassword}
                     autoComplete="new-password" minLength={minLength} />
      <PasswordField label="Repeat new password" value={repeat} onChange={setRepeat} autoComplete="new-password"
                     matches={password} />
    </SheetForm>
  );
}
