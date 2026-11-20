import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "border border-ocean-700 bg-ocean-700 text-white hover:border-ocean-800 hover:bg-ocean-800 active:bg-ocean-900",
  secondary: "border border-slate-300 bg-white text-ink hover:border-slate-400 hover:bg-slate-50 active:bg-slate-100",
  danger: "border border-rose-700 bg-rose-700 text-white hover:border-rose-800 hover:bg-rose-800 active:bg-rose-900",
  ghost: "border border-transparent bg-transparent text-slate-600 hover:bg-slate-100 hover:text-ink active:bg-slate-200",
};

const sizes: Record<Size, string> = {
  sm: "min-h-8 px-3 py-1.5 text-xs",
  md: "min-h-10 px-4 py-2 text-sm",
  lg: "min-h-11 px-5 py-2.5 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  loadingLabel,
  className = "",
  disabled,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  loadingLabel?: string;
}) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 ${sizes[size]} ${variants[variant]} ${className}`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  );
}
