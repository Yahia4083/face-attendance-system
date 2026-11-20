import { Download } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card, SectionHeader } from "../../components/common/Card";
import { Field, inputClass } from "../../components/common/Form";
import { PageHeader } from "../../components/common/PageHeader";
import { DataTable } from "../../components/common/Table";
import { ErrorState, LoadingState } from "../../components/common/State";
import { useToast } from "../../components/common/Toast";
import { exportMyAttendanceReport, getMyAttendanceSummary } from "../../api/employeeSelfService";
import { useAsync } from "../../hooks/useAsync";
import type { ReportRow } from "../../types/api";
import { downloadBlob, filenameFromContentDisposition } from "../../utils/downloads";
import { getErrorMessage } from "../../utils/errors";
import { formatDate, formatDateTime, todayIsoDate } from "../../utils/dateTime";

function defaultRange() {
  // Builds the default report date range for the current month.
  const today = todayIsoDate();
  const [year, month] = today.split("-").map(Number);
  const date_from = `${year}-${String(month).padStart(2, "0")}-01`;
  return { date_from, date_to: today };
}

function SummaryCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="border-b border-slate-200 p-4 sm:border-r">
      <p className="data-label">{title}</p>
      <p className="mt-2 font-display text-xl font-semibold tabular-nums text-ink">{value}</p>
    </div>
  );
}

export function MyReportsPage() {
  const { notify } = useToast();
  const [range, setRange] = useState(defaultRange);
  const [exporting, setExporting] = useState<string | null>(null);
  // Loads the authenticated employee's personal report summary.
  const report = useAsync(() => getMyAttendanceSummary(range), [range.date_from, range.date_to]);

  async function exportReport(format: "csv" | "xlsx") {
    setExporting(format);
    try {
      // Downloads the authenticated employee's personal report export.
      const response = await exportMyAttendanceReport({ ...range, format });
      const filename = filenameFromContentDisposition(
        response.headers["content-disposition"],
        `my_attendance_${range.date_from}_to_${range.date_to}.${format}`,
      );
      downloadBlob(response.data, filename);
      notify(`Downloaded ${format.toUpperCase()} report.`, "success");
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader title="My Reports" description="Review your personal attendance summary and export only your own records." />
      <Card>
        <SectionHeader title="Report period" description="Choose a date range, then download a CSV or Excel copy when needed." />
        <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto_auto] md:items-end">
          <Field label="Date from">
            <input className={inputClass} type="date" value={range.date_from} onChange={(event) => setRange((current) => ({ ...current, date_from: event.target.value }))} />
          </Field>
          <Field label="Date to">
            <input className={inputClass} type="date" value={range.date_to} onChange={(event) => setRange((current) => ({ ...current, date_to: event.target.value }))} />
          </Field>
          <Button variant="secondary" onClick={() => exportReport("csv")} disabled={Boolean(exporting)} loading={exporting === "csv"} loadingLabel="Downloading...">
            <Download className="h-4 w-4" />
            CSV
          </Button>
          <Button variant="secondary" onClick={() => exportReport("xlsx")} disabled={Boolean(exporting)} loading={exporting === "xlsx"} loadingLabel="Downloading...">
            <Download className="h-4 w-4" />
            XLSX
          </Button>
        </div>
      </Card>

      {report.loading ? (
        <LoadingState label="Loading personal report..." />
      ) : report.error ? (
        <ErrorState message={report.error} />
      ) : report.data ? (
        <>
          <Card>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-display text-lg font-semibold text-ink">Summary</h2>
                <p className="text-sm text-slate-500">
                  {formatDate(report.data.date_from)} to {formatDate(report.data.date_to)} - {report.data.timezone}
                </p>
              </div>
              {report.data.requires_daily_processing_for_complete_absence_metrics ? (
                <Badge value="PENDING" label="Processing affects absence metrics" />
              ) : null}
            </div>
            <div className="mt-4 grid overflow-hidden rounded-md border border-slate-300 sm:grid-cols-2 xl:grid-cols-5 [&>*:last-child]:border-r-0">
              <SummaryCard title="Total records" value={report.data.summary.total_records ?? 0} />
              <SummaryCard title="Late" value={report.data.summary.late_count ?? 0} />
              <SummaryCard title="Absent" value={report.data.summary.absent_count ?? 0} />
              <SummaryCard title="Missing checkout" value={report.data.summary.missing_checkout_count ?? 0} />
              <SummaryCard
                title="Attendance rate"
                value={report.data.summary.attendance_rate_percentage == null ? "N/A" : `${report.data.summary.attendance_rate_percentage}%`}
              />
            </div>
          </Card>

          <Card>
            <SectionHeader title="Report records" />
            <div>
              <DataTable<ReportRow>
                rowKey={(row) => row.attendance_id}
                rows={report.data.records ?? []}
                emptyTitle="No attendance records found"
                empty="No attendance records were returned for this selected report period."
                columns={[
                  { header: "Date", render: (row) => formatDate(row.schedule_date) },
                  { header: "Schedule", render: (row) => row.schedule_template_name ?? "Unscheduled" },
                  { header: "Check in", render: (row) => formatDateTime(row.check_in_at) },
                  { header: "Check out", render: (row) => formatDateTime(row.check_out_at) },
                  { header: "Status", render: (row) => <Badge value={row.status} /> },
                  { header: "Justification", render: (row) => (row.latest_justification_status ? <Badge value={row.latest_justification_status} /> : "None") },
                  { header: "Overtime", render: (row) => (row.latest_overtime_status ? <Badge value={row.latest_overtime_status} /> : "None") },
                ]}
              />
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}
