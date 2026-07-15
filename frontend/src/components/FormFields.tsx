import { Button, NativeSelect, TextInput } from "@mantine/core";
import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "color"> & { label: string; hint?: string };
export function Field({ label, hint, ...props }: FieldProps) {
  return <TextInput label={label} description={hint} radius="md" {...props} />;
}

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size" | "color"> & { label: string };
export function SelectField({ label, children, ...props }: SelectProps) {
  return <NativeSelect label={label} radius="md" {...props}>{children}</NativeSelect>;
}

export function SubmitButton({ busy, children }: { busy: boolean; children: string }) {
  return <Button className="submit-button" type="submit" loading={busy} radius="md">{children}</Button>;
}
