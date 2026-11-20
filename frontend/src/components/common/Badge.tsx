const statusColors: Record<string, string> = {
  PRESENT: "border-emerald-200 bg-emerald-50 text-emerald-800",
  LATE: "border-amber-200 bg-amber-50 text-amber-800",
  ABSENT: "border-rose-200 bg-rose-50 text-rose-800",
  EARLY_DEPARTURE: "border-orange-200 bg-orange-50 text-orange-800",
  MISSING_CHECKOUT: "border-rose-200 bg-rose-50 text-rose-800",
  UNSCHEDULED: "border-sky-200 bg-sky-50 text-sky-800",
  PENDING: "border-amber-200 bg-amber-50 text-amber-800",
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  REJECTED: "border-rose-200 bg-rose-50 text-rose-800",
  ACTIVE: "border-emerald-200 bg-emerald-50 text-emerald-800",
  INACTIVE: "border-slate-300 bg-slate-100 text-slate-700",
  JUSTIFICATION: "border-sky-200 bg-sky-50 text-sky-800",
  OVERTIME: "border-ocean-200 bg-ocean-50 text-ocean-800",
};

const statusDots: Record<string, string> = {
  PRESENT: "bg-emerald-600",
  LATE: "bg-amber-600",
  ABSENT: "bg-rose-600",
  EARLY_DEPARTURE: "bg-orange-600",
  MISSING_CHECKOUT: "bg-rose-600",
  UNSCHEDULED: "bg-sky-600",
  PENDING: "bg-amber-600",
  APPROVED: "bg-emerald-600",
  REJECTED: "bg-rose-600",
  ACTIVE: "bg-emerald-600",
  INACTIVE: "bg-slate-500",
  JUSTIFICATION: "bg-sky-600",
  OVERTIME: "bg-ocean-600",
};

export function Badge({ value, label }: { value?: string | boolean | null; label?: string }) {
  const key = typeof value === "boolean" ? (value ? "ACTIVE" : "INACTIVE") : String(value ?? "UNKNOWN");
  const color = statusColors[key] ?? "border-slate-300 bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[0.6875rem] font-semibold leading-none ${color}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDots[key] ?? "bg-slate-500"}`} aria-hidden="true" />
      {label ?? formatEnumLabel(key)}
    </span>
  );
}
import { formatEnumLabel } from "../../utils/formatters";
