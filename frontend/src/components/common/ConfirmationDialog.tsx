import { AlertTriangle } from "lucide-react";
import { Button } from "./Button";
import { Modal } from "./Modal";

export function ConfirmationDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "primary",
  loading = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      size="sm"
      footer={
        <div className="action-row">
          <Button variant="secondary" onClick={onClose} disabled={loading}>{cancelLabel}</Button>
          <Button variant={tone} onClick={onConfirm} loading={loading} loadingLabel="Working...">{confirmLabel}</Button>
        </div>
      }
    >
      <div className="flex items-start gap-4">
        <div className={`rounded-md p-2.5 ${tone === "danger" ? "bg-rose-50 text-rose-700" : "bg-ocean-50 text-ocean-700"}`}>
          <AlertTriangle className="h-6 w-6" aria-hidden="true" />
        </div>
        <p className="pt-1 text-sm leading-relaxed text-slate-600">{description}</p>
      </div>
    </Modal>
  );
}
