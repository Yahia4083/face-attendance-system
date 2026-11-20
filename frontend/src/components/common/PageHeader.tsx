export function PageHeader({
  title,
  description,
  eyebrow,
  action,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-slate-300 pb-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-4xl border-l-[3px] border-signal-600 pl-3">
        {eyebrow ? <p className="subtle-label">{eyebrow}</p> : null}
        <h1 className={`${eyebrow ? "mt-1" : ""} font-display text-xl font-semibold tracking-tight text-ink sm:text-2xl`}>
          {title}
        </h1>
        {description ? <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}
