import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";

const tones = {
  info: { classes: "border-sky-200 bg-sky-50 text-sky-800", Icon: Info },
  success: { classes: "border-emerald-200 bg-emerald-50 text-emerald-800", Icon: CheckCircle2 },
  warning: { classes: "border-amber-200 bg-amber-50 text-amber-800", Icon: TriangleAlert },
  danger: { classes: "border-rose-200 bg-rose-50 text-rose-800", Icon: AlertCircle },
};

export function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: keyof typeof tones;
  title?: string;
  children: React.ReactNode;
}) {
  const { classes, Icon } = tones[tone];
  return (
    <div className={`flex items-start gap-3 rounded-md border-l-4 p-3.5 text-sm ${classes}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 leading-relaxed">
        {title ? <p className="font-bold">{title}</p> : null}
        <div className={title ? "mt-1" : ""}>{children}</div>
      </div>
    </div>
  );
}
