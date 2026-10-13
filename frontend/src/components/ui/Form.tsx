/**
 * Form controls.
 *
 * In plain words: every input is paired with a visible <label> (so screen readers
 * announce it), an optional hint, and an error message tied to the input with
 * aria-describedby. Touch targets are at least 40px tall.
 */
import clsx from "clsx";
import { cloneElement, isValidElement, useId, type InputHTMLAttributes, type ReactElement, type ReactNode, type SelectHTMLAttributes } from "react";

const CONTROL =
  "w-full min-h-10 rounded-md border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-3 " +
  "disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-70 aria-[invalid=true]:border-bad";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
  className?: string;
}

/** Wraps a single control with its label, hint and error. */
export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {isValidElement(children) && cloneElement(children, { id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p id={hintId} className="text-xs text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-medium text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(CONTROL, className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(CONTROL, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export function Checkbox({ label, hint, className, ...rest }: { label: ReactNode; hint?: ReactNode } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const id = useId();
  return (
    <div className={clsx("flex items-start gap-3", className)}>
      <input id={id} type="checkbox" className="mt-0.5 size-5 shrink-0 rounded border-line-strong accent-[var(--brand)]" aria-describedby={hint ? `${id}-hint` : undefined} {...rest} />
      <div>
        <label htmlFor={id} className="text-sm text-ink">
          {label}
        </label>
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-ink-3">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

/** Segmented choice (radio group) - e.g. "fixed recall" vs "fixed FAR". */
export function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; hint?: string }[];
}) {
  const name = useId();
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{label}</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((option) => (
          <label
            key={option.value}
            className={clsx(
              "flex min-h-10 cursor-pointer items-start gap-2.5 rounded-md border p-3 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--focus)]",
              value === option.value ? "border-ink bg-surface-2" : "border-line-strong hover:bg-surface-2",
            )}
          >
            <input type="radio" name={name} className="mt-0.5 accent-[var(--brand)]" checked={value === option.value} onChange={() => onChange(option.value)} />
            <span>
              <span className="font-medium">{option.label}</span>
              {option.hint && <span className="block text-xs text-ink-3">{option.hint}</span>}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
