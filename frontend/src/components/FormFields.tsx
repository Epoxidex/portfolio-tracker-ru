import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

export function Field({ label, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return <label className="form-field"><span>{label}</span><input {...props} />{hint && <small>{hint}</small>}</label>;
}

export function SelectField({ label, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  return <label className="form-field"><span>{label}</span><select {...props}>{children}</select></label>;
}

export function SubmitButton({ busy, children }: { busy: boolean; children: string }) {
  return <button className="primary-button submit-button" type="submit" disabled={busy}>{busy ? "Выполняем…" : children}</button>;
}
