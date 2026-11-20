import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "../../components/common/Button";
import { Field, inputClass } from "../../components/common/Form";
import { ErrorState } from "../../components/common/State";
import { PortalLoginShell } from "../../components/layout/PortalLoginShell";
import { useAuth } from "../../contexts/AuthContext";
import { getErrorMessage } from "../../utils/errors";

type LoginForm = {
  email: string;
  password: string;
};

export function EmployeeLoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { register, handleSubmit } = useForm<LoginForm>();

  if (user?.role === "EMPLOYEE") {
    return (
      <Navigate
        to={user.must_change_password ? "/employee/change-password" : "/employee"}
        replace
      />
    );
  }
  if (user?.role === "ADMIN") return <Navigate to="/" replace />;

  async function onSubmit(values: LoginForm) {
    setLoading(true);
    setError(null);
    try {
      const loggedInUser = await login(values.email, values.password, {
        requiredRole: "EMPLOYEE",
        portalName: "employee portal",
      });
      navigate(
        loggedInUser.must_change_password
          ? "/employee/change-password"
          : "/employee",
        { replace: true },
      );
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalLoginShell
      portalLabel="Employee Self-Service"
      title="Your Attendance Record"
      description="Review camera-generated attendance, assigned schedules, personal reports, and request decisions through a private employee workspace."
      accessNote="This portal provides no manual check-in or check-out controls."
    >
      <section className="rounded-lg border border-slate-300 bg-white shadow-card">
        <div className="border-b border-slate-200 px-6 py-5">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-signal-700">Employee Portal</p>
          <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Employee sign in</h2>
          <p className="mt-1.5 text-sm text-slate-500">Access only your own attendance information.</p>
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
              Sign in to employee portal
            </Button>
          </form>
          <p className="mt-5 border-t border-slate-200 pt-5 text-center text-xs text-slate-500">
            Administrator?{" "}
            <Link className="font-semibold text-ocean-700 hover:underline" to="/login">
              Sign in to admin portal
            </Link>
          </p>
        </div>
      </section>
    </PortalLoginShell>
  );
}
