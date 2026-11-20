import { useNavigate } from "react-router-dom";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <Card className="max-w-lg text-center">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-ocean-600">Page not found</p>
        <h1 className="mt-3 font-display text-3xl font-bold text-ink">This admin page does not exist.</h1>
        <p className="mt-3 text-sm text-slate-500">
          The administrative portal only exposes supported management, reporting, review, and configuration pages.
        </p>
        <div className="mt-6 flex justify-center">
          <Button onClick={() => navigate("/")}>Return to dashboard</Button>
        </div>
      </Card>
    </div>
  );
}
