import { LockKeyhole, ScanFace, ShieldCheck } from "lucide-react";

export function PortalLoginShell({
  portalLabel,
  title,
  description,
  accessNote,
  children,
}: {
  portalLabel: string;
  title: string;
  description: string;
  accessNote: string;
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-slate-100 lg:grid lg:grid-cols-[minmax(22rem,0.78fr)_minmax(32rem,1.22fr)]">
      <section className="relative flex min-h-[20rem] flex-col justify-between overflow-hidden border-b-4 border-signal-500 bg-ocean-900 px-6 py-7 text-white lg:min-h-screen lg:border-b-0 lg:border-r-4 lg:px-10 lg:py-10">
        <div>
          <div className="flex items-center gap-3 border-b border-white/15 pb-5">
            <div className="relative grid h-11 w-11 place-items-center rounded-md border border-signal-300/40 bg-signal-700">
              <ScanFace className="h-6 w-6" aria-hidden="true" />
              <span className="absolute -bottom-px left-2 right-2 h-px bg-signal-300" />
            </div>
            <div>
              <p className="text-[0.625rem] font-semibold uppercase tracking-[0.18em] text-signal-200">Identity Operations</p>
              <p className="mt-0.5 text-sm font-semibold">Face Attendance Registry</p>
            </div>
          </div>

          <div className="mt-10 max-w-xl lg:mt-20">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal-200">{portalLabel}</p>
            <h1 className="mt-3 font-display text-3xl font-semibold leading-tight text-white lg:text-4xl">{title}</h1>
            <p className="mt-5 max-w-lg text-sm leading-7 text-slate-300">{description}</p>
          </div>
        </div>

        <div className="mt-8 border-t border-white/15 pt-5">
          <div className="grid gap-4 text-xs text-slate-300 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            <div className="flex items-start gap-2.5">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-signal-300" aria-hidden="true" />
              <span>Role-restricted access enforced by the backend.</span>
            </div>
            <div className="flex items-start gap-2.5">
              <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-signal-300" aria-hidden="true" />
              <span>{accessNote}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="flex min-h-[calc(100vh-20rem)] items-center justify-center bg-slate-100 px-4 py-10 sm:px-8 lg:min-h-screen lg:py-14">
        <div className="w-full max-w-md">
          {children}
          <p className="mt-5 text-center text-[0.6875rem] uppercase tracking-[0.12em] text-slate-500">
            Attendance Recognition System · Africa/Tripoli
          </p>
        </div>
      </section>
    </main>
  );
}
