import { useEffect, useMemo, useState } from "react";

export type FieldType = "text" | "textarea" | "number" | "list" | "i18n-text" | "i18n-textarea" | "checkbox";

export interface FieldDef {
  name: string;          // base field name
  label: string;
  type: FieldType;
  i18nName?: string;     // map field name, required for i18n-* types
  required?: boolean;
  placeholder?: string;
  rows?: number;
}

interface EntityFormProps<T> {
  fields: FieldDef[];
  initial: T;
  onSubmit: (data: T) => void | Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
  errors?: { field: string; message: string }[];
  submitLabel?: string;
  busy?: boolean;
}

function valuesEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null || b == null) return a === b;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => valuesEqual(v, b[i]));
  }
  if (typeof a === "object" && typeof b === "object") {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) return false;
    return aKeys.every((key) =>
      valuesEqual(
        (a as Record<string, unknown>)[key],
        (b as Record<string, unknown>)[key],
      ),
    );
  }
  return false;
}

function isEmptyValue(value: unknown, type: FieldType): boolean {
  if (value === undefined || value === null) return true;
  if (type === "list") return Array.isArray(value) && value.length === 0;
  if (type === "checkbox") return value !== true;
  if (type === "number") return value === "" || Number.isNaN(Number(value));
  return String(value).trim() === "";
}

const I18N_TYPES: FieldType[] = ["i18n-text", "i18n-textarea"];
const LANGUAGE_CODE_RE = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/;

function isI18nType(type: FieldType): boolean {
  return I18N_TYPES.includes(type);
}

function i18nFieldNames(fields: FieldDef[]): string[] {
  return fields
    .filter((f) => isI18nType(f.type) && f.i18nName)
    .map((f) => f.i18nName!);
}

function allLanguages(values: Record<string, unknown>, names: string[]): string[] {
  const set = new Set<string>();
  for (const name of names) {
    const map = values[name] as Record<string, string> | undefined;
    if (map) Object.keys(map).forEach((k) => set.add(k));
  }
  return Array.from(set).sort();
}

export function EntityForm<T extends Record<string, unknown>>({
  fields,
  initial,
  onSubmit,
  onDirtyChange,
  errors,
  submitLabel = "Save",
  busy = false,
}: EntityFormProps<T>) {
  const [values, setValues] = useState<T>(initial);
  const [localErrors, setLocalErrors] = useState<{ field: string; message: string }[]>([]);
  const [activeLang, setActiveLang] = useState<string>("en");

  const i18nNames = useMemo(() => i18nFieldNames(fields), [fields]);
  const languages = useMemo(() => allLanguages(values, i18nNames), [values, i18nNames]);

  useEffect(() => {
    setValues(initial);
    setLocalErrors([]);
    setActiveLang("en");
  }, [initial]);

  const dirty = !valuesEqual(values, initial);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const setField = (name: keyof T, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const validate = (next: T) => {
    const nextErrors: { field: string; message: string }[] = [];
    for (const field of fields) {
      if (field.required && isEmptyValue(next[field.name], field.type)) {
        nextErrors.push({ field: field.name, message: `${field.label} is required` });
      }
    }
    return nextErrors;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const nextErrors = validate(values);
    setLocalErrors(nextErrors);
    if (nextErrors.length === 0) {
      onSubmit(values);
    }
  };

  const fieldErrors = (name: string) =>
    [...(errors ?? []), ...localErrors].filter((err) => err.field === name) ?? [];

  return (
    <form onSubmit={handleSubmit} className="admin-form">
      {i18nNames.length > 0 && (
        <div className="qc-field">
          <span className="qc-field__label">Language</span>
          <div className="qc-lang-toggle" role="group" aria-label="Language">
            <button
              type="button"
              className={`qc-btn ${activeLang === "en" ? "qc-btn--primary" : "qc-btn--secondary"}`}
              onClick={() => setActiveLang("en")}
            >
              EN
            </button>
            {languages.map((code) => (
              <button
                key={code}
                type="button"
                className={`qc-btn ${activeLang === code ? "qc-btn--primary" : "qc-btn--secondary"}`}
                onClick={() => setActiveLang(code)}
              >
                {code.toUpperCase()}
              </button>
            ))}
            <button
              type="button"
              className="qc-btn qc-btn--secondary"
              onClick={() => {
                const code = window.prompt("Language code (e.g. de, sr, zh-cn):")
                  ?.trim()
                  .toLowerCase();
                if (!code || !LANGUAGE_CODE_RE.test(code)) {
                  window.alert("Invalid language code.");
                  return;
                }
                if (code === "en") {
                  window.alert("'en' is reserved for the base language.");
                  return;
                }
                setActiveLang(code);
                const next: Record<string, unknown> = { ...values };
                for (const name of i18nNames) {
                  const map = (next[name] as Record<string, string> | undefined) || {};
                  if (!(code in map)) next[name] = { ...map, [code]: "" };
                }
                setValues(next as T);
              }}
            >
              + Add language
            </button>
          </div>
        </div>
      )}
      {fields.map((field) => {
        const errorsForField = fieldErrors(field.name);
        const hasErrors = errorsForField.length > 0;
        return (
          <div
            key={field.name}
            className={`qc-field ${hasErrors ? "qc-field--error" : ""}`}
          >
            {field.type === "checkbox" ? (
              <label className="admin-check">
                <input
                  id={`field-${field.name}`}
                  type="checkbox"
                  checked={values[field.name] === true}
                  onChange={(e) => setField(field.name, e.target.checked)}
                  aria-required={field.required ? "true" : undefined}
                  aria-invalid={hasErrors ? "true" : undefined}
                />
                {field.label}
              </label>
            ) : (
              <label className="qc-field__label" htmlFor={`field-${field.name}`}>
                {field.label}
              </label>
            )}
            {(field.type === "text" || (field.type === "i18n-text" && activeLang === "en")) && (
              <input
                id={`field-${field.name}`}
                className="qc-input"
                type="text"
                value={String(values[field.name] ?? "")}
                onChange={(e) => setField(field.name, e.target.value)}
                aria-required={field.required ? "true" : undefined}
                aria-invalid={hasErrors ? "true" : undefined}
                placeholder={field.placeholder}
              />
            )}
            {field.type === "i18n-text" && activeLang !== "en" && (
              <input
                id={`field-${field.name}-${activeLang}`}
                className="qc-input"
                type="text"
                value={String((values[field.i18nName!] as Record<string, string> | undefined)?.[activeLang] ?? "")}
                onChange={(e) => {
                  const map = (values[field.i18nName!] as Record<string, string> | undefined) || {};
                  const next = { ...map, [activeLang]: e.target.value };
                  if (!e.target.value.trim()) delete next[activeLang];
                  setField(field.i18nName!, next);
                }}
                placeholder={`${field.label} (${activeLang})`}
              />
            )}
            {(field.type === "textarea" || (field.type === "i18n-textarea" && activeLang === "en")) && (
              <textarea
                id={`field-${field.name}`}
                className="qc-input"
                value={String(values[field.name] ?? "")}
                onChange={(e) => setField(field.name, e.target.value)}
                aria-required={field.required ? "true" : undefined}
                aria-invalid={hasErrors ? "true" : undefined}
                placeholder={field.placeholder}
                rows={field.rows ?? 4}
              />
            )}
            {field.type === "i18n-textarea" && activeLang !== "en" && (
              <textarea
                id={`field-${field.name}-${activeLang}`}
                className="qc-input"
                value={String((values[field.i18nName!] as Record<string, string> | undefined)?.[activeLang] ?? "")}
                onChange={(e) => {
                  const map = (values[field.i18nName!] as Record<string, string> | undefined) || {};
                  const next = { ...map, [activeLang]: e.target.value };
                  if (!e.target.value.trim()) delete next[activeLang];
                  setField(field.i18nName!, next);
                }}
                placeholder={`${field.label} (${activeLang})`}
                rows={field.rows ?? 4}
              />
            )}
            {field.type === "number" && (
              <input
                id={`field-${field.name}`}
                className="qc-input"
                type="number"
                value={String(values[field.name] ?? "")}
                onChange={(e) => setField(field.name, Number(e.target.value))}
                aria-required={field.required ? "true" : undefined}
                aria-invalid={hasErrors ? "true" : undefined}
                placeholder={field.placeholder}
              />
            )}
            {field.type === "list" && (
              <ListField
                values={(values[field.name] as string[] | undefined) ?? []}
                onChange={(items) => setField(field.name, items)}
                label={field.label}
              />
            )}
            {errorsForField.map((err) => (
              <p key={err.message} className="qc-field__error">
                {err.message}
              </p>
            ))}
          </div>
        );
      })}
      <button className="qc-btn qc-btn--primary" type="submit" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}

function ListField({
  values,
  onChange,
  label,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  label: string;
}) {
  const update = (index: number, value: string) => {
    const next = [...values];
    next[index] = value;
    onChange(next);
  };

  const remove = (index: number) => {
    const next = values.filter((_, i) => i !== index);
    onChange(next);
  };

  const add = () => {
    onChange([...values, ""]);
  };

  return (
    <div className="admin-list-field">
      {values.map((value, index) => (
        <div key={index} className="admin-list-row">
          <input
            className="qc-input"
            type="text"
            value={value}
            onChange={(e) => update(index, e.target.value)}
            aria-label={`${label} ${index + 1}`}
          />
          <button
            type="button"
            className="qc-btn qc-btn--secondary"
            onClick={() => remove(index)}
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" className="qc-btn qc-btn--secondary" onClick={add}>
        Add {label}
      </button>
    </div>
  );
}
