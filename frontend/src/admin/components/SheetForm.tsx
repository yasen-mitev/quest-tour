import { useEffect, useId, type ReactNode } from "react";

interface SheetFormProps {
  title: string;
  /** One or two sentences under the title: what happens on submit. */
  note: ReactNode;
  submitLabel: string;
  busy?: boolean;
  /** Validation or server error, shown inside the sheet so the admin can correct and retry. */
  error?: string | null;
  onSubmit: () => void;
  onCancel: () => void;
  children: ReactNode;
}

/** A form in the confirmation sheet (same look as ConfirmDialog): Enter submits, Escape and the
 *  scrim cancel. The caller focuses its first field. */
export function SheetForm({ title, note, submitLabel, busy = false, error = null, onSubmit, onCancel, children }: SheetFormProps) {
  const titleId = useId();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="qs-overlay qc-scrim" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <form className="qc-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId}
            onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        <h2 className="qc-sheet__title" id={titleId}>{title}</h2>
        <p className="qc-sheet__body">{note}</p>
        {children}
        {error && <p className="qc-field__error" role="alert">{error}</p>}
        <div className="qc-sheet__actions">
          <button type="submit" disabled={busy} className="qc-btn qc-btn--primary qc-btn--block">{submitLabel}</button>
          <button type="button" className="qc-btn qc-btn--secondary qc-btn--block" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
