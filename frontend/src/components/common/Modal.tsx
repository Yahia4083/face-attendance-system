import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Button } from "./Button";

const sizeClasses = {
  sm: "max-w-lg",
  md: "max-w-2xl",
  lg: "max-w-3xl",
  xl: "max-w-5xl",
};

export function Modal({
  open,
  title,
  children,
  onClose,
  footer,
  description,
  size = "lg",
  closeOnBackdrop = false,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  footer?: React.ReactNode;
  description?: string;
  size?: keyof typeof sizeClasses;
  closeOnBackdrop?: boolean;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const selector = "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])";
    const focusable = () => Array.from(panel?.querySelectorAll<HTMLElement>(selector) ?? []);
    focusable()[0]?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      const dialogs = Array.from(document.querySelectorAll<HTMLElement>("[role='dialog']"));
      if (dialogs[dialogs.length - 1] !== panel) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-3 sm:p-6"
      onMouseDown={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={`max-h-[calc(100vh-1.5rem)] w-full overflow-hidden rounded-xl border border-slate-400 bg-white shadow-elevated sm:max-h-[90vh] ${sizeClasses[size]}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-300 bg-slate-50 px-5 py-4 sm:px-6">
          <div>
            <h2 id={titleId} className="font-display text-lg font-semibold text-ink">{title}</h2>
            {description ? <p id={descriptionId} className="mt-1 text-sm leading-relaxed text-slate-500">{description}</p> : null}
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close dialog" className="shrink-0 px-2">
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="max-h-[calc(90vh-10rem)] overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        {footer ? <div className="border-t border-slate-300 bg-slate-50 px-5 py-3.5 sm:px-6">{footer}</div> : null}
      </div>
    </div>
  );
}
