import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useContext, useMemo, useState } from "react";

type Toast = { id: number; message: string; tone: "success" | "error" | "info" };

const ToastContext = createContext<{ notify: (message: string, tone?: Toast["tone"]) => void } | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = (id: number) => setToasts((items) => items.filter((item) => item.id !== id));
  const value = useMemo(
    () => ({
      notify: (message: string, tone: Toast["tone"] = "info") => {
        const id = Date.now() + Math.random();
        setToasts((items) => [...items, { id, message, tone }]);
        window.setTimeout(() => dismiss(id), 4500);
      },
    }),
    [],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 top-4 z-[60] flex flex-col items-end gap-3 sm:left-auto sm:w-96" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex w-full items-start gap-3 rounded-md border-l-4 px-4 py-3 text-sm font-semibold shadow-elevated ring-1 ${
              toast.tone === "success"
                ? "border-emerald-600 bg-emerald-50 text-emerald-800 ring-emerald-200"
                : toast.tone === "error"
                  ? "border-rose-600 bg-rose-50 text-rose-800 ring-rose-200"
                  : "border-ocean-600 bg-white text-slate-700 ring-slate-300"
            }`}
          >
            {toast.tone === "success" ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /> : toast.tone === "error" ? <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" /> : <Info className="mt-0.5 h-5 w-5 shrink-0" />}
            <span className="flex-1 leading-relaxed">{toast.message}</span>
            <button type="button" onClick={() => dismiss(toast.id)} className="rounded-lg p-1 hover:bg-black/5" aria-label="Dismiss notification">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}
