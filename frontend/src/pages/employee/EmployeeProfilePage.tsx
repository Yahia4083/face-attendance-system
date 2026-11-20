import { UserRound } from "lucide-react";
import { Badge } from "../../components/common/Badge";
import { ChangePasswordForm } from "../../components/employee/ChangePasswordForm";
import { Alert } from "../../components/common/Alert";
import { Card, SectionHeader } from "../../components/common/Card";
import { PageHeader } from "../../components/common/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../../components/common/State";
import { getMyAttendanceSummary, getMyEffectiveSchedule } from "../../api/employeeSelfService";
import { useAuth } from "../../contexts/AuthContext";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime, todayIsoDate } from "../../utils/dateTime";

function currentMonthRange() {
  const today = todayIsoDate();
  const [year, month] = today.split("-").map(Number);
  return {
    date_from: `${year}-${String(month).padStart(2, "0")}-01`,
    date_to: today,
  };
}

function InfoCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-b border-slate-200 bg-white px-3.5 py-3 sm:border-r">
      <p className="data-label">{label}</p>
      <div className="data-value font-semibold">{value}</div>
    </div>
  );
}

export function EmployeeProfilePage() {
  const { user } = useAuth();
  const today = todayIsoDate();
  // Loads the employee profile summary and current schedule snapshot.
  const summary = useAsync(() => getMyAttendanceSummary(currentMonthRange()), []);
  const schedule = useAsync(() => getMyEffectiveSchedule(today), [today]);

  const employeeName = summary.data?.employee_name ?? schedule.data?.employee_name ?? "Employee";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Profile"
        title={employeeName}
        description={user?.email ?? "Employee account"}
        action={<div className="grid h-10 w-10 place-items-center rounded-md border border-ocean-200 bg-ocean-50 text-ocean-700"><UserRound className="h-5 w-5" aria-hidden="true" /></div>}
      />

      {summary.loading || schedule.loading ? (
        <LoadingState label="Loading profile information..." />
      ) : summary.error ? (
        <ErrorState message={summary.error} />
      ) : schedule.error ? (
        <ErrorState message={schedule.error} />
      ) : (
        <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
          <Card>
            <SectionHeader title="Employee details" />
            <div className="grid overflow-hidden rounded-md border border-slate-300 sm:grid-cols-2">
              <InfoCard label="Full name" value={employeeName} />
              <InfoCard label="Employee number" value={summary.data?.employee_number ?? "Not available"} />
              <InfoCard label="Department" value={summary.data?.department_name ?? "Not available"} />
              <InfoCard label="Email address" value={user?.email ?? "Not available"} />
              <InfoCard label="Role" value={<Badge value={user?.role ?? "EMPLOYEE"} />} />
              <InfoCard label="Account status" value={<Badge value={Boolean(user?.is_active)} />} />
            </div>
          </Card>

          <Card>
            <SectionHeader title="Current schedule snapshot" />
            {schedule.data?.has_schedule ? (
              <div className="grid overflow-hidden rounded-md border border-slate-300 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                <InfoCard label="Schedule" value={schedule.data.schedule_template_name ?? "Not available"} />
                <InfoCard label="Scheduled start" value={formatDateTime(schedule.data.scheduled_start_datetime)} />
                <InfoCard label="Scheduled end" value={formatDateTime(schedule.data.scheduled_end_datetime)} />
                <InfoCard label="Timezone" value={schedule.data.timezone ?? "Africa/Tripoli"} />
              </div>
            ) : (
              <div className="mt-5">
                <EmptyState title="No active schedule today" description={schedule.data?.message ?? "No schedule is currently resolved for today."} />
              </div>
            )}
          </Card>
        </section>
      )}

      <Alert tone="info">
        Profile editing is not shown because the inspected backend does not expose an employee self-update endpoint. Contact an administrator for profile corrections.
      </Alert>
      <ChangePasswordForm />
    </div>
  );
}
