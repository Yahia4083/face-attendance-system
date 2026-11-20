import { LogOut, Menu, ScanFace, ShieldCheck, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { Button } from "../common/Button";

export type PortalNavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  group?: string;
};

function Sidebar({ portalLabel, brandTitle, navItems, footerText, onNavigate }: {
  portalLabel: string;
  brandTitle: string;
  navItems: PortalNavItem[];
  footerText: string;
  onNavigate?: () => void;
}) {
  let previousGroup: string | undefined;
  return (
    <aside className="flex h-full flex-col border-r border-ocean-800 bg-ocean-900 text-white">
      <div className="border-b border-white/10 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="relative grid h-10 w-10 shrink-0 place-items-center rounded-md border border-signal-400/40 bg-signal-700 text-white">
            <ScanFace className="h-5 w-5" aria-hidden="true" />
            <span className="absolute -bottom-px left-2 right-2 h-px bg-signal-300" />
          </div>
          <div className="min-w-0">
            <p className="text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-signal-200">{portalLabel}</p>
            <h1 className="mt-0.5 font-display text-sm font-semibold leading-tight text-white">{brandTitle}</h1>
          </div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-2.5 py-3" aria-label={`${portalLabel} navigation`}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const showGroup = item.group && item.group !== previousGroup;
          previousGroup = item.group;
          return (
            <div key={item.to}>
              {showGroup ? <p className="mb-1 mt-4 px-3 text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-slate-500 first:mt-0">{item.group}</p> : null}
              <NavLink
                to={item.to}
                end={item.to === "/" || item.to === "/employee"}
                onClick={onNavigate}
                className={({ isActive }) => `relative mb-0.5 flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-[0.8125rem] font-medium transition-colors ${isActive ? "bg-white/[0.1] text-white before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:bg-signal-300" : "text-slate-300 hover:bg-white/[0.06] hover:text-white"}`}
              >
                <Icon className="h-4 w-4 shrink-0" strokeWidth={1.8} aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            </div>
          );
        })}
      </nav>
      <div className="border-t border-white/10 px-4 py-3.5">
        <div className="flex items-start gap-2.5 text-[0.6875rem] leading-relaxed text-slate-400">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-300" aria-hidden="true" />
          <p>{footerText}</p>
        </div>
      </div>
    </aside>
  );
}

export function PortalLayout({ portalLabel, headerEyebrow, brandTitle, navItems, footerText, sidebarWidth = "280px" }: {
  portalLabel: string;
  headerEyebrow: string;
  brandTitle: string;
  navItems: PortalNavItem[];
  footerText: string;
  sidebarWidth?: string;
}) {
  const [open, setOpen] = useState(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const title = navItems.find((item) => item.to === location.pathname)?.label ?? portalLabel;

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);

  return (
    <div className="min-h-screen lg:grid" style={{ gridTemplateColumns: `${sidebarWidth} minmax(0, 1fr)` }}>
      <div className="hidden h-screen lg:sticky lg:top-0 lg:block">
        <Sidebar portalLabel={portalLabel} brandTitle={brandTitle} navItems={navItems} footerText={footerText} />
      </div>
      {open ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" className="absolute inset-0 bg-slate-950/60" onClick={() => setOpen(false)} aria-label="Close navigation" />
          <div className="relative h-full w-72 max-w-[86vw] shadow-elevated">
            <button type="button" onClick={() => setOpen(false)} className="absolute right-3 top-3 z-10 rounded-md bg-white/10 p-2 text-white hover:bg-white/20" aria-label="Close navigation menu">
              <X className="h-5 w-5" />
            </button>
            <Sidebar portalLabel={portalLabel} brandTitle={brandTitle} navItems={navItems} footerText={footerText} onNavigate={() => setOpen(false)} />
          </div>
        </div>
      ) : null}
      <main className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-slate-300 bg-white px-4 sm:px-5 lg:px-6">
          <div className="flex min-h-16 items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <Button size="sm" variant="secondary" className="px-2.5 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
                <Menu className="h-5 w-5" />
              </Button>
              <div className="min-w-0">
                <p className="hidden text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-500 sm:block">{headerEyebrow}</p>
                <h2 className="truncate font-display text-base font-semibold text-ink sm:text-lg">{title}</h2>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2 sm:gap-3">
              <div className="hidden items-center gap-3 border-r border-slate-200 pr-3 md:flex">
                <div className="grid h-8 w-8 place-items-center rounded-md bg-ocean-900 text-xs font-semibold text-white">
                  {user?.email?.slice(0, 2).toUpperCase() ?? "US"}
                </div>
                <div className="text-left">
                  <p className="max-w-56 truncate text-xs font-semibold text-ink">{user?.email}</p>
                  <p className="text-[0.6875rem] uppercase tracking-wide text-slate-500">{user?.role?.toLowerCase()}</p>
                </div>
              </div>
              <Button size="sm" variant="secondary" onClick={logout}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </div>
          </div>
        </header>
        <div className="mx-auto max-w-[112rem] px-4 py-5 sm:px-5 lg:px-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
