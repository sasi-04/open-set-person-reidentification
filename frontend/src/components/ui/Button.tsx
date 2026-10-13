/**
 * Button.
 *
 * In plain words: one button component for the whole app, so every button has the same
 * shape (pill, like zed.digital), the same visible keyboard focus, and the same
 * loading/disabled behaviour. A loading button is disabled (no double submits) and
 * announces itself as busy to screen readers.
 */
import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "dark";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-on-brand hover:bg-brand-strong border border-transparent",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-surface-2",
  ghost: "bg-transparent text-ink-2 border border-transparent hover:bg-surface-2",
  danger: "bg-surface text-bad border border-bad hover:bg-bad-bg",
  dark: "bg-ink text-canvas border border-transparent hover:opacity-90",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, icon, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-medium whitespace-nowrap transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});
