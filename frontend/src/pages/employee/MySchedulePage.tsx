import { CalendarDays, Clock, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Alert } from "../../components/common/Alert";
import { Card, SectionHeader } from "../../components/common/Card";
import { Field, inputClass } from "../../components/common/Form";
import { PageHeader } from "../../components/common/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../../components/common/State";
import { getMyEffectiveSchedule } from "../../api/employeeSelfService";
import { useAsync } from "../../hooks/useAsync";
import { formatDate, formatDateTime, todayIsoDate } from "../../utils/dateTime";

export function MySchedulePage() {
  const [onDate, setOnDate] = useState(todayIsoDate());
  // Loads the effective schedule for the selected date.
  const schedule = useAsync(() => getMyEffectiveSchedule(onDate), [onDate]);

  return (
    <div className="page-stack">
      <PageHeader
        title="My Schedule"
        description="View the effective schedule assignment resolved for a selected business date."
        action={<div className="w-full sm:w-64">
          <Field label="Schedule date" hint={`Selected: ${formatDate(onDate)}`}>
            <input className={inputClass} type="date" value={onDate} onChange={(event) => setOnDate(event.target.value)} />
          </Field>
        </div>}
      />

      {schedule.loading ? (
        <LoadingState label="Loading your effective schedule..." />
      ) : schedule.error ? (
        <ErrorState message={schedule.error} />
      ) : !schedule.data?.has_schedule ? (
        <EmptyState title="No active schedule found" description={schedule.data?.message ?? "No effective schedule is assigned for the selected date."} />
      ) : (
        <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
          <Card>
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
              <div>
                <p className="subtle-label">Effective Schedule</p>
                <h2 className="mt-1 font-display text-xl font-semibold text-ink">{schedule.data.schedule_template_name}</h2>
                <p className="mt-2 text-sm text-slate-500">For {formatDate(schedule.data.on_date)}</p>
              </div>
              <Badge value={schedule.data.working_day} label={schedule.data.working_day ? "Working day" : "Non-working day"} />
            </div>

            <div className="mt-4 grid overflow-hidden rounded-md border border-slate-300 sm:grid-cols-2">
              <div className="border-b border-slate-200 p-4 sm:border-r">
                <Clock className="h-5 w-5 text-ocean-700" />
                <p className="mt-3 data-label">Scheduled start</p>
                <p className="data-value font-semibold">{formatDateTime(schedule.data.scheduled_start_datetime)}</p>
              </div>
              <div className="border-b border-slate-200 p-4">
                <Clock className="h-5 w-5 text-ocean-700" />
                <p className="mt-3 data-label">Scheduled end</p>
                <p className="data-value font-semibold">{formatDateTime(schedule.data.scheduled_end_datetime)}</p>
              </div>
              <div className="p-4 sm:border-r">
                {schedule.data.is_overnight ? <Moon className="h-5 w-5 text-ocean-700" /> : <Sun className="h-5 w-5 text-ocean-700" />}
                <p className="mt-3 data-label">Shift type</p>
                <p className="data-value font-semibold">{schedule.data.is_overnight ? "Overnight shift" : "Daytime shift"}</p>
              </div>
              <div className="p-4">
                <CalendarDays className="h-5 w-5 text-ocean-700" />
                <p className="mt-3 data-label">Timezone</p>
                <p className="data-value font-semibold">{schedule.data.timezone ?? "Africa/Tripoli"}</p>
              </div>
            </div>
          </Card>

          <Card>
            <SectionHeader title="Attendance policy details" />
            <dl className="divide-y divide-slate-200 border-y border-slate-200 text-sm">
              {/* Renders schedule policy details for the selected date. */}
              <div className="flex items-center justify-between gap-4 py-3">
                <dt className="font-medium text-slate-500">Check-in grace</dt>
                <dd className="font-semibold text-ink">{schedule.data.check_in_grace_minutes ?? 0} minutes</dd>
              </div>
              <div className="flex items-center justify-between gap-4 py-3">
                <dt className="font-medium text-slate-500">Early departure tolerance</dt>
                <dd className="font-semibold text-ink">{schedule.data.early_departure_tolerance_minutes ?? 0} minutes</dd>
              </div>
            </dl>
            <div className="mt-4">
              <Alert tone="info">
                Attendance is still recorded by the connected recognition camera. This page is informational only.
              </Alert>
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}
