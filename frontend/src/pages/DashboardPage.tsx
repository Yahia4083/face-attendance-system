import { Activity, AlertTriangle, Building2, Clock3, Database, FileQuestion, Users } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getAttendanceTrend, getDashboardAttendance, getDashboardSummary, getDepartmentDashboard, getPendingRequests, getRecentActivity } from "../api/dashboard";
import { Badge } from "../components/common/Badge";
import { Alert } from "../components/common/Alert";
import { Card, SectionHeader } from "../components/common/Card";
import { Field, inputClass } from "../components/common/Form";
import { PageHeader } from "../components/common/PageHeader";
import { DataTable } from "../components/common/Table";
import { EmptyState, ErrorState, LoadingState } from "../components/common/State";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, formatIsoDatePreview, todayIsoDate } from "../utils/dateTime";
import { useState } from "react";

function MetricCell({ title, value, icon: Icon, hint }: { title: string; value: string | number; icon: typeof Users; hint?: string }) {
  return (
    <div className="min-h-28 border-b border-slate-200 p-4 sm:border-r xl:min-h-32 xl:p-5">
      <div className="flex items-center gap-2 text-slate-500">
        <Icon className="h-4 w-4 text-signal-700" strokeWidth={1.8} aria-hidden="true" />
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em]">{title}</p>
      </div>
      <p className="mt-3 break-words font-display text-2xl font-semibold leading-none tabular-nums text-ink 2xl:text-[1.75rem]">{value}</p>
      {hint ? <p className="mt-2 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function DashboardPage() {
  const [onDate, setOnDate] = useState(todayIsoDate());
  // Loads dashboard data for the selected business date.
  const summary = useAsync(() => getDashboardSummary(onDate), [onDate]);
  const attendance = useAsync(() => getDashboardAttendance({ on_date: onDate, page: 1, page_size: 6 }), [onDate]);
  const pending = useAsync(() => getPendingRequests({ page: 1, page_size: 5 }), [onDate]);
  const departments = useAsync(() => getDepartmentDashboard({ on_date: onDate, page: 1, page_size: 8 }), [onDate]);
  const trend = useAsync(() => getAttendanceTrend({ days: 7, end_date: onDate }), [onDate]);
  const activity = useAsync(() => getRecentActivity(8), [onDate]);

  if (summary.loading) return <LoadingState label="Loading dashboard..." />;
  if (summary.error || !summary.data) return <ErrorState message={summary.error ?? "Dashboard unavailable"} />;

  const data = summary.data;
  // Reads the backend attendance-rate value for display.
  const attendanceRate = data.attendance.attendance_rate_percentage;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Operations overview"
        title={data.organization_name}
        description="Live administrative overview built from existing attendance and workflow records."
        action={
          <div className="w-full sm:w-56">
            <Field label="Business date" hint={formatIsoDatePreview(onDate)}>
            <input
              type="date"
              value={onDate}
              onChange={(event) => setOnDate(event.target.value)}
              className={inputClass}
            />
            </Field>
          </div>
        }
      />

      <div className="operations-strip" aria-label="Dashboard data context">
        <span><strong className="font-semibold text-ink">Timezone:</strong> {data.timezone}</span>
        <span><strong className="font-semibold text-ink">Generated:</strong> {formatDateTime(data.generated_at)}</span>
        <span className="inline-flex items-center gap-1.5"><Database className="h-3.5 w-3.5 text-signal-700" /> Existing attendance records</span>
      </div>

      {data.requires_daily_processing_for_complete_absence_metrics ? (
        // Displays the dashboard data-basis notice.
        <Alert tone="warning" title="Attendance processing notice">
          Absence and missing-checkout figures are based on existing attendance records. Run daily processing for completed shifts before treating absence metrics as final.
        </Alert>
      ) : null}

      <section className="overflow-hidden rounded-lg border border-slate-300 bg-white shadow-card" aria-labelledby="attendance-indicators-title">
        <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-4 py-3">
          <div>
            <h2 id="attendance-indicators-title" className="text-sm font-semibold text-ink">Operational indicators</h2>
            <p className="mt-0.5 text-xs text-slate-500">Attendance values are scoped to {formatIsoDatePreview(onDate)}.</p>
          </div>
          <span className="border-l-2 border-signal-600 pl-2 text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-500">Daily status</span>
        </div>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 [&>*:nth-child(2n)]:sm:border-r-0 [&>*:nth-child(4n)]:xl:border-r-0">
          <MetricCell title="Active Employees" value={data.employees.active_employee_count} icon={Users} />
          <MetricCell title="Present On Time" value={data.attendance.present_on_time_count} icon={Clock3} />
          <MetricCell title="Late" value={data.attendance.late_count} icon={AlertTriangle} />
          <MetricCell title="Absent" value={data.attendance.absent_count} icon={FileQuestion} />
          <MetricCell title="Missing Checkout" value={data.attendance.missing_checkout_count} icon={Activity} />
          <MetricCell title="Unscheduled" value={data.attendance.unscheduled_attendance_count} icon={Clock3} />
          <MetricCell title="Pending Requests" value={data.requests.total_pending_request_count} icon={FileQuestion} hint="Current review queue" />
          <MetricCell title="Attendance Rate" value={attendanceRate === null ? "Unavailable" : `${attendanceRate}%`} icon={Building2} hint="Scheduled records only" />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Card>
          <SectionHeader title="Seven-day Attendance Trend" description="Existing processed attendance records only." />
          {trend.loading ? <LoadingState label="Loading attendance trend..." /> : trend.error ? <ErrorState message={trend.error} /> : <div className="h-72">
            {/* Renders backend trend values in the chart. */}
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend.data?.items ?? []} margin={{ top: 8, right: 10, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#d8e0e8" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={{ stroke: "#cbd5e1" }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ borderRadius: 6, borderColor: "#cbd5e1", boxShadow: "0 4px 12px rgba(15,31,48,.1)" }} />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
                <Line type="monotone" dataKey="scheduled_attended_shift_count" name="Attended" stroke="#168487" strokeWidth={2.5} dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
                <Line type="monotone" dataKey="absent_count" name="Absent" stroke="#b93942" strokeWidth={2} dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>}
        </Card>
        <Card>
          <SectionHeader title="Recent Activity" />
          {activity.loading ? <LoadingState label="Loading recent activity..." /> : activity.error ? <ErrorState message={activity.error} /> : (activity.data?.items ?? []).length === 0 ? (
            <EmptyState title="No recent attendance activity" description="New attendance and request activity will appear here." />
          ) : (
            <div className="divide-y divide-slate-200 border-y border-slate-200">
              {(activity.data?.items ?? []).map((item) => (
                <div key={`${item.activity_type}-${item.related_entity_id}-${item.occurred_at}`} className="relative py-3 pl-4 before:absolute before:left-0 before:top-[1.15rem] before:h-1.5 before:w-1.5 before:bg-signal-600">
                  <p className="text-xs font-semibold leading-5 text-ink">{item.description}</p>
                  <p className="mt-0.5 text-[0.6875rem] text-slate-500">{item.employee_name ?? "System"} · {formatDateTime(item.occurred_at)}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <SectionHeader title="Attendance Preview" />
          <DataTable
            rows={attendance.data?.items ?? []}
            rowKey={(row) => row.attendance_id}
            emptyTitle="No attendance records for this date"
            empty="Attendance recorded by the camera workflow will appear here."
            columns={[
              { header: "Employee", render: (row) => <span className="font-semibold">{row.employee_name}</span> },
              { header: "Status", render: (row) => <Badge value={row.status} /> },
              { header: "In", render: (row) => formatDateTime(row.check_in_at) },
              { header: "Out", render: (row) => formatDateTime(row.check_out_at) },
            ]}
          />
        </Card>
        <Card>
          <SectionHeader title="Pending Review Queue" />
          <DataTable
            rows={pending.data?.items ?? []}
            rowKey={(row) => `${row.request_category}-${row.request_id}`}
            emptyTitle="No requests waiting for review"
            empty="The current administrative review queue is clear."
            columns={[
              { header: "Type", render: (row) => <Badge value={row.request_category} /> },
              { header: "Employee", render: (row) => row.employee_name },
              { header: "Status", render: (row) => <Badge value={row.status} /> },
              { header: "Created", render: (row) => formatDateTime(row.created_at) },
            ]}
          />
        </Card>
      </div>

      <Card>
        <SectionHeader title="Department Overview" description="Active departments are shown, including zero-value departments." />
        <DataTable
          rows={departments.data?.items ?? []}
          rowKey={(row) => row.department_id}
          emptyTitle="No department attendance data"
          empty="Active departments will appear when dashboard data is available."
          columns={[
            { header: "Department", render: (row) => <span className="font-semibold">{row.department_name}</span> },
            { header: "Active Employees", render: (row) => row.active_employee_count },
            { header: "Absent", render: (row) => row.absent_count },
            { header: "Late", render: (row) => row.late_count },
            { header: "Rate", render: (row) => row.attendance_rate_percentage === null ? "Unavailable" : `${row.attendance_rate_percentage}%` },
          ]}
        />
      </Card>
    </div>
  );
}


