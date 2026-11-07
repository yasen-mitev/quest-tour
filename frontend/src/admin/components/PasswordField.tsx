import { useEffect, useId, useState, type Ref } from "react";
import { Icon } from "../../components/Icon";

/** How long a revealed password stays readable before it is masked again. */
export const REVEAL_MS = 5000;

interface PasswordFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  required?: boolean;
  ref?: Ref<HTMLInputElement>;
}

/** A labelled password input with an eye button that shows the typed password for a few seconds.
 *  The button sits beside the input, not inside the <label>: a label may hold only one control. */
export function PasswordField({ label, value, onChange, autoComplete, required = true, ref }: PasswordFieldProps) {
  const id = useId();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!shown) return;
    const timer = window.setTimeout(() => setShown(false), REVEAL_MS);
    return () => window.clearTimeout(timer);
  }, [shown]);

  return (
    <div className="qc-field">
      <label className="qc-field__label" htmlFor={id}>{label}</label>
      <div className="admin-password">
        <input ref={ref} id={id} className="qc-input" type={shown ? "text" : "password"} value={value}
               required={required} autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="admin-password__toggle" aria-controls={id}
                aria-label={shown ? "Hide password" : "Show password"} onClick={() => setShown((s) => !s)}>
          <Icon name={shown ? "eyeOff" : "eye"} />
        </button>
      </div>
    </div>
  );
}
