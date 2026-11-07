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
  /** Shows the length rule under the field, updated while typing (new passwords). */
  minLength?: number;
  /** Makes this the repeat field: once typed in, says whether it matches this value. */
  matches?: string;
  ref?: Ref<HTMLInputElement>;
}

type Rule = { text: string; met: boolean; done: string };

function currentRule(value: string, minLength?: number, matches?: string): Rule | null {
  if (minLength !== undefined) {
    const base = `At least ${minLength} characters`;
    const missing = minLength - value.length;
    const met = missing <= 0;
    return { text: met || value.length === 0 ? base : `${base} (${missing} more)`, met, done: `${base}: done` };
  }
  if (matches !== undefined && value.length > 0) {
    const met = value === matches;
    return { text: met ? "Passwords match" : "Doesn't match yet", met, done: "Passwords match: done" };
  }
  return null;
}

/** A labelled password input with an eye button that shows the typed password for a few seconds,
 *  and optionally a live rule underneath (length, or matching the first entry). The rule starts
 *  neutral and turns green when met; it never shows an error while typing — submit still checks.
 *  The button sits beside the input, not inside the <label>: a label may hold only one control. */
export function PasswordField({
  label, value, onChange, autoComplete, required = true, minLength, matches, ref,
}: PasswordFieldProps) {
  const id = useId();
  const ruleId = `${id}-rule`;
  const [shown, setShown] = useState(false);
  const rule = currentRule(value, minLength, matches);
  const hasRule = minLength !== undefined || matches !== undefined;

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
               required={required} autoComplete={autoComplete} aria-describedby={rule ? ruleId : undefined}
               onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="admin-password__toggle" aria-controls={id}
                aria-label={shown ? "Hide password" : "Show password"} onClick={() => setShown((s) => !s)}>
          <Icon name={shown ? "eyeOff" : "eye"} />
        </button>
      </div>
      {rule && (
        <p id={ruleId} className={rule.met ? "admin-rule admin-rule--met" : "admin-rule"}>
          <Icon name={rule.met ? "check" : "ring"} />
          {rule.text}
        </p>
      )}
      {/* Announced only when the rule flips to met; the visible hint is read with the field. */}
      {hasRule && <span role="status" className="admin-sr-only">{rule?.met ? rule.done : ""}</span>}
    </div>
  );
}
