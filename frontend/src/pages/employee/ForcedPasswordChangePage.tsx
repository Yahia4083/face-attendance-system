import { LogOut } from "lucide-react";
import { ChangePasswordForm } from "../../components/employee/ChangePasswordForm";
import { Button } from "../../components/common/Button";
import { useAuth } from "../../contexts/AuthContext";

export function ForcedPasswordChangePage() {
  const { logout, user } = useAuth();

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto max-w-xl space-y-5">
        <div className="flex items-center justify-between gap-4 rounded-lg bg-ink px-6 py-5 text-white shadow-card">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ocean-100">
              Employee Account Security
            </p>
            <p className="mt-2 text-sm text-slate-300">{user?.email}</p>
          </div>
          <Button variant="secondary" onClick={logout}>
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
        <ChangePasswordForm forced />
      </div>
    </main>
  );
}
