import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "../components/common/Button";
import { Field, inputClass } from "../components/common/Form";
import { ErrorState } from "../components/common/State";
import { PortalLoginShell } from "../components/layout/PortalLoginShell";
import { useAuth } from "../contexts/AuthContext";
import { getErrorMessage } from "../utils/errors";

type LoginForm = {
  email: string;
  password: string;
};

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { register, handleSubmit } = useForm<LoginForm>();

  if (user?.role === "ADMIN") return <Navigate to="/" replace />;

  async function onSubmit(values: LoginForm) {
    setLoading(true);
    setError(null);
    try {
      await login(values.email, values.password, {
        requiredRole: "ADMIN",
        portalName: "administrative portal",
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalLoginShell
      portalLabel="Administrative Access"
      title="Attendance Operations Console"
      description="Manage workforce records, attendance exceptions, schedules, reports, security policies, and system audit history from one controlled workspace."
      accessNote="Camera attendance remains separate from this administrative portal."
    >
      <section className="rounded-lg border border-slate-300 bg-white shadow-card">
        <div className="border-b border-slate-200 px-6 py-5">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ocean-700">Admin Portal</p>
          <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Authorized sign in</h2>
          <p className="mt-1.5 text-sm text-slate-500">Use an administrator account to continue.</p>
        </div>
        <div className="px-6 py-6">
          <form className="space-y-4" onSubmit={handleSubmit(onSubmit)}>
            <Field label="Email address" required>
              <input className={inputClass} type="email" autoComplete="email" required {...register("email")} />
            </Field>
            <Field label="Password" required>
              <input className={inputClass} type="password" autoComplete="current-password" required {...register("password")} />
            </Field>
            {error ? <ErrorState message={error} /> : null}
            <Button type="submit" className="w-full" loading={loading} loadingLabel="Signing in...">
              Sign in to admin portal
            </Button>
          </form>
          <div className="mt-5 border-t border-slate-200 pt-5 text-center">
            <p className="text-xs text-slate-600">Are you an employee?</p>
            <Link
              to="/employee/login"
              className="mt-2 inline-flex min-h-9 items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-ocean-700 transition hover:border-ocean-500 hover:bg-ocean-50"
            >
              Go to Employee Self-Service
            </Link>
          </div>
        </div>
      </section>
    </PortalLoginShell>
  );
}
