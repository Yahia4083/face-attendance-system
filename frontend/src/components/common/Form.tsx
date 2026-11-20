import { cloneElement, isValidElement, useId, type ReactElement } from "react";

export function Field({
  label,
  children,
  hint,
  error,
  required = false,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  error?: string;
  required?: boolean;
}) {
  const messageId = useId();
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error || hint ? messageId : undefined,
      })
    : children;

  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-700">
        {label}
        {required ? <span className="ml-1 text-rose-600" aria-label="required">*</span> : null}
      </span>
      {control}
      {error ? <span id={messageId} className="mt-1.5 block text-xs font-semibold leading-relaxed text-rose-600">{error}</span> : null}
      {!error && hint ? <span id={messageId} className="mt-1.5 block text-xs leading-relaxed text-slate-500">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "min-h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink shadow-none transition-colors placeholder:text-slate-400 focus:border-signal-600 focus:ring-2 focus:ring-signal-100 disabled:bg-slate-100 disabled:text-slate-500 aria-[invalid=true]:border-rose-500 aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-rose-100";

export function FormErrorSummary({ messages }: { messages: string[] }) {
  const uniqueMessages = Array.from(new Set(messages.filter(Boolean)));
  if (!uniqueMessages.length) return null;
  return (
    <div className="rounded-md border-l-4 border-rose-600 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert" aria-live="polite">
      <p className="font-semibold">Please fix the following before continuing:</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {uniqueMessages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}
