import { AlertCircle, Inbox, Loader2 } from "lucide-react";

export function LoadingState({ label = "Loading data..." }: { label?: string }) {
  return (
    <div className="flex min-h-28 items-center justify-center gap-3 rounded-md border border-dashed border-slate-400 bg-slate-50 p-5 text-sm font-medium text-slate-600" role="status" aria-live="polite">
      <Loader2 className="h-5 w-5 animate-spin text-ocean-600" />
      {label}
    </div>
  );
}

export function EmptyState({ title = "No data found", description, action }: { title?: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-slate-400 bg-slate-50 p-6 text-center">
      <Inbox className="mx-auto h-7 w-7 text-slate-400" aria-hidden="true" />
      <p className="mt-3 font-semibold text-slate-700">{title}</p>
      {description ? <p className="mt-1 text-sm text-slate-500">{description}</p> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-md border-l-4 border-rose-600 bg-rose-50 p-3.5 text-sm font-medium text-rose-800" role="alert">
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
