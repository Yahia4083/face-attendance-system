import { useState } from "react";
import { exportAttendanceReport, getDailyReport, getDepartmentSummary, getEmployeeSummary, getMonthlyReport } from "../api/reports";
import { listDepartments } from "../api/departments";
import { listEmployees } from "../api/employees";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { Field, inputClass } from "../components/common/Form";
import { PageHeader } from "../components/common/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/common/State";
import { DataTable } from "../components/common/Table";
import { useToast } from "../components/common/Toast";
import { useAsync } from "../hooks/useAsync";
import type { Employee, ReportSummary } from "../types/api";
import { filenameFromContentDisposition, downloadBlob } from "../utils/downloads";
import { getErrorMessage } from "../utils/errors";
import { formatDateTime, formatIsoDatePreview, todayIsoDate, toInputMonth } from "../utils/dateTime";

type ReportType = "ALL" | "EMPLOYEE" | "DEPARTMENT";

type LoadedSummary = {
  title: string;
  subtitle: string;
  summary: ReportSummary;
};

const reportTypeOptions: { value: ReportType; label: string; description: string }[] = [
  {
    value: "ALL",
    label: "All Records",
    description: "Export attendance records for the selected date range.",
  },
  {
    value: "EMPLOYEE",
    label: "Employee Report",
    description: "View attendance summary for one employee using their employee number.",
  },
  {
    value: "DEPARTMENT",
    label: "Department Report",
    description: "View attendance summary for one department.",
  },
];

export function ReportsPage() {
  const { notify } = useToast();
  const [reportType, setReportType] = useState<ReportType>("ALL");
  const [dailyDate, setDailyDate] = useState(todayIsoDate());
  const [month, setMonth] = useState(toInputMonth());
  const [departmentId, setDepartmentId] = useState("");
  const [dateFrom, setDateFrom] = useState(`${todayIsoDate().slice(0, 7)}-01`);
  const [dateTo, setDateTo] = useState(todayIsoDate());
  const [employeeNumber, setEmployeeNumber] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [employeeLookupMessage, setEmployeeLookupMessage] = useState("");
  const [employeeLookupLoading, setEmployeeLookupLoading] = useState(false);
  const [summaryResult, setSummaryResult] = useState<LoadedSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "xlsx" | null>(null);

  const departments = useAsync(() => listDepartments({ page: 1, page_size: 100 }), []);
  const daily = useAsync(() => getDailyReport({ on_date: dailyDate, page: 1, page_size: 25 }), [dailyDate]);
  const monthly = useAsync(() => {
    const [year, monthPart] = month.split("-");
    return getMonthlyReport({ year, month: monthPart, page: 1, page_size: 25 });
  }, [month]);

  const selectedDepartment = departments.data?.items.find((item) => String(item.id) === departmentId) ?? null;
  const dateRangeError =
    dateFrom && dateTo && dateFrom > dateTo ? "Date from must be earlier than or equal to date to." : "";
  const dateRangeValid = Boolean(dateFrom && dateTo && !dateRangeError);
  const activeReportType = reportTypeOptions.find((item) => item.value === reportType) ?? reportTypeOptions[0];

  function changeReportType(nextType: ReportType) {
    setReportType(nextType);
    setSummaryResult(null);
  }

  function updateDateFrom(value: string) {
    setDateFrom(value);
    setSummaryResult(null);
  }

  function updateDateTo(value: string) {
    setDateTo(value);
    setSummaryResult(null);
  }

  async function resolveEmployeeNumber() {
    const normalized = employeeNumber.trim();
    setSelectedEmployee(null);
    setEmployeeLookupMessage("");
    setSummaryResult(null);

    if (!normalized) {
      setEmployeeLookupMessage("Enter an employee number, for example EMP001.");
      return;
    }

    setEmployeeLookupLoading(true);
    try {
      // Resolves an employee by employee number for report filters.
      const result = await listEmployees({ search: normalized, page: 1, page_size: 10 });
      const exact = result.items.find((item) => item.employee_number.toLowerCase() === normalized.toLowerCase());
      if (!exact) {
        setEmployeeLookupMessage("No employee found with this employee number.");
        return;
      }
      setSelectedEmployee(exact);
      setEmployeeLookupMessage("Employee found.");
    } catch (err) {
      setEmployeeLookupMessage(getErrorMessage(err));
    } finally {
      setEmployeeLookupLoading(false);
    }
  }

  function reportFilters(format: "csv" | "xlsx") {
    // Builds backend export filters for the selected report type.
    return {
      date_from: dateFrom,
      date_to: dateTo,
      employee_id: reportType === "EMPLOYEE" ? selectedEmployee?.id : undefined,
      department_id: reportType === "DEPARTMENT" ? departmentId || undefined : undefined,
      format,
    };
  }

  async function download(format: "csv" | "xlsx") {
    if (!dateRangeValid) {
      notify(dateRangeError || "Select a valid date range first.", "error");
      return;
    }
    if (reportType === "EMPLOYEE" && !selectedEmployee) {
      notify("Please enter and resolve an employee number before downloading an employee report.", "error");
      return;
    }
    if (reportType === "DEPARTMENT" && !departmentId) {
      notify("Please select a department before downloading a department report.", "error");
      return;
    }

    setExporting(format);
    try {
      // Downloads the generated backend report file.
      const response = await exportAttendanceReport(reportFilters(format));
      downloadBlob(response.data, filenameFromContentDisposition(response.headers["content-disposition"], `attendance-report.${format}`));
      notify(`${format.toUpperCase()} export downloaded.`, "success");
    } catch {
      notify("Could not download the report. Please check the selected filters and try again.", "error");
    } finally {
      setExporting(null);
    }
  }

  async function loadEmployeeSummary() {
    if (!selectedEmployee) {
      notify("Please enter and resolve an employee number before generating an employee report.", "error");
      return;
    }
    if (!dateRangeValid) {
      notify(dateRangeError || "Select a valid date range first.", "error");
      return;
    }

    setSummaryLoading(true);
    try {
      // Loads the selected employee attendance summary.
      const data = await getEmployeeSummary(selectedEmployee.id, { date_from: dateFrom, date_to: dateTo });
      setSummaryResult({
        title: "Employee Summary",
        subtitle: `${selectedEmployee.full_name} (${selectedEmployee.employee_number})`,
        summary: data.summary,
      });
      notify("Employee summary loaded.", "success");
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setSummaryLoading(false);
    }
  }

  async function loadDepartmentSummary() {
    if (!departmentId || !selectedDepartment) {
      notify("Please select a department before generating a department report.", "error");
      return;
    }
    if (!dateRangeValid) {
      notify(dateRangeError || "Select a valid date range first.", "error");
      return;
    }

    setSummaryLoading(true);
    try {
      // Loads the selected department attendance summary.
      const data = await getDepartmentSummary(Number(departmentId), { date_from: dateFrom, date_to: dateTo, page: 1, page_size: 10 });
      setSummaryResult({
        title: "Department Summary",
        subtitle: selectedDepartment.name,
        summary: data.summary,
      });
      notify("Department summary loaded.", "success");
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setSummaryLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Reports and Export"
        description="Review backend-calculated attendance summaries and download audit-logged CSV or Excel files."
      />
      <Card>
        <SectionHeader
          title="Choose report scope"
          description="Only fields relevant to the selected report type are shown."
        />
        <div className="grid gap-3 md:grid-cols-3">
          {reportTypeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={reportType === option.value}
              onClick={() => changeReportType(option.value)}
              className={`min-h-28 rounded-md border p-4 text-left transition-colors ${
                reportType === option.value
                  ? "border-ocean-500 bg-ocean-50 text-ocean-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-ocean-300"
              }`}
            >
              <span className="block font-semibold">{option.label}</span>
              <span className="mt-1 block text-sm">{option.description}</span>
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <SectionHeader title={activeReportType.label} description={activeReportType.description} />
        <DateRangeFields
          dateFrom={dateFrom}
          dateTo={dateTo}
          error={dateRangeError}
          onDateFromChange={updateDateFrom}
          onDateToChange={updateDateTo}
        />

        {reportType === "ALL" ? (
          <ReportActionBlock
            title="All attendance records"
            description="Export attendance records for the selected date range."
            actions={
              <>
                <Button onClick={() => download("csv")} disabled={!dateRangeValid || Boolean(exporting)} loading={exporting === "csv"} loadingLabel="Preparing CSV...">Download CSV</Button>
                <Button variant="secondary" onClick={() => download("xlsx")} disabled={!dateRangeValid || Boolean(exporting)} loading={exporting === "xlsx"} loadingLabel="Preparing XLSX...">Download XLSX</Button>
              </>
            }
          />
        ) : null}

        {reportType === "EMPLOYEE" ? (
          <div className="mt-5 space-y-4">
            <div className="rounded-md border border-slate-200 p-4">
              <Field label="Employee number" required hint="Enter the employee number, then click Find.">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    className={inputClass}
                    value={employeeNumber}
                    onChange={(event) => {
                      setEmployeeNumber(event.target.value);
                      setSelectedEmployee(null);
                      setEmployeeLookupMessage("");
                      setSummaryResult(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        resolveEmployeeNumber();
                      }
                    }}
                    placeholder="Enter employee number, for example EMP001"
                  />
                  <Button type="button" variant="secondary" onClick={resolveEmployeeNumber} loading={employeeLookupLoading} loadingLabel="Searching...">
                    Find
                  </Button>
                </div>
              </Field>
              {employeeLookupMessage ? (
                <p className={`mt-2 text-sm font-semibold ${selectedEmployee ? "text-emerald-700" : "text-amber-700"}`}>
                  {employeeLookupMessage}
                </p>
              ) : null}
              {selectedEmployee ? <EmployeeSummaryCard employee={selectedEmployee} /> : null}
            </div>

            <ReportActionBlock
              title="Employee report"
              description="View or export attendance data for the resolved employee."
              actions={
                <>
                  <Button onClick={loadEmployeeSummary} disabled={!dateRangeValid || !selectedEmployee || summaryLoading}>
                    {summaryLoading ? "Loading..." : "View employee summary"}
                  </Button>
                  <Button variant="secondary" onClick={() => download("csv")} disabled={!dateRangeValid || !selectedEmployee || Boolean(exporting)} loading={exporting === "csv"}>Download employee CSV</Button>
                  <Button variant="secondary" onClick={() => download("xlsx")} disabled={!dateRangeValid || !selectedEmployee || Boolean(exporting)} loading={exporting === "xlsx"}>Download employee XLSX</Button>
                </>
              }
            />
          </div>
        ) : null}

        {reportType === "DEPARTMENT" ? (
          <div className="mt-5 space-y-4">
            <Field label="Department" required>
              <select
                className={inputClass}
                value={departmentId}
                onChange={(event) => {
                  setDepartmentId(event.target.value);
                  setSummaryResult(null);
                }}
              >
                <option value="">Choose department</option>
                {departments.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </Field>
            {departments.loading ? <LoadingState label="Loading departments..." /> : null}
            {departments.error ? <ErrorState message={departments.error} /> : null}

            <ReportActionBlock
              title="Department report"
              description="View or export attendance data for the selected department."
              actions={
                <>
                  <Button onClick={loadDepartmentSummary} disabled={!dateRangeValid || !departmentId || summaryLoading}>
                    {summaryLoading ? "Loading..." : "View department summary"}
                  </Button>
                  <Button variant="secondary" onClick={() => download("csv")} disabled={!dateRangeValid || !departmentId || Boolean(exporting)} loading={exporting === "csv"}>Download department CSV</Button>
                  <Button variant="secondary" onClick={() => download("xlsx")} disabled={!dateRangeValid || !departmentId || Boolean(exporting)} loading={exporting === "xlsx"}>Download department XLSX</Button>
                </>
              }
            />
          </div>
        ) : null}

        {summaryResult ? <LoadedSummaryCard result={summaryResult} /> : null}
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <SectionHeader title="Daily Attendance Preview" action={<input className={inputClass} type="date" value={dailyDate} onChange={(e) => setDailyDate(e.target.value)} />} />
          <p className="mb-4 text-xs text-slate-500">{formatIsoDatePreview(dailyDate)}</p>
          {daily.loading ? <LoadingState /> : daily.error ? <ErrorState message={daily.error} /> : (
            <>
              <ReportSummaryGrid summary={daily.data?.summary} />
              <DataTable rowKey={(row) => row.attendance_id} rows={daily.data?.items ?? []} columns={[
                { header: "Employee", render: (row) => row.employee_name },
                { header: "Status", render: (row) => <Badge value={row.status} /> },
                { header: "In", render: (row) => formatDateTime(row.check_in_at) },
                { header: "Out", render: (row) => formatDateTime(row.check_out_at) },
              ]} emptyTitle="No attendance records found for this day." empty="Try selecting another date." />
            </>
          )}
        </Card>
        <Card>
          <SectionHeader title="Monthly Attendance Preview" action={<input className={inputClass} type="month" value={month} onChange={(e) => setMonth(e.target.value)} />} />
          {monthly.loading ? <LoadingState /> : monthly.error ? <ErrorState message={monthly.error} /> : (
            <>
              <ReportSummaryGrid summary={monthly.data?.summary} />
              <DataTable rowKey={(row) => row.employee_id} rows={monthly.data?.items ?? []} columns={[
                { header: "Employee", render: (row) => row.employee_name },
                { header: "Absent", render: (row) => row.absent_count },
                { header: "Late", render: (row) => row.late_count },
                { header: "Rate", render: (row) => row.attendance_rate_percentage === null ? "Unavailable" : `${row.attendance_rate_percentage}%` },
              ]} emptyTitle="No monthly attendance rows found." empty="Try selecting another month." />
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function DateRangeFields({
  dateFrom,
  dateTo,
  error,
  onDateFromChange,
  onDateToChange,
}: {
  dateFrom: string;
  dateTo: string;
  error: string;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
}) {
  return (
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      <Field label="Date from" required hint={formatIsoDatePreview(dateFrom)} error={error}>
        <input className={inputClass} type="date" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} />
      </Field>
      <Field label="Date to" required hint={formatIsoDatePreview(dateTo)}>
        <input className={inputClass} type="date" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} />
      </Field>
    </div>
  );
}

function EmployeeSummaryCard({ employee }: { employee: Employee }) {
  return (
    <div className="mt-4 rounded-md bg-ocean-50 p-4 text-sm text-ocean-800">
      <p className="font-bold text-ink">{employee.full_name}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Info label="Employee number" value={employee.employee_number} />
        <Info label="Department" value={employee.department_name} />
        <Info label="Status" value={<Badge value={employee.is_active} />} />
      </div>
    </div>
  );
}

function ReportActionBlock({ title, description, actions }: { title: string; description: string; actions: React.ReactNode }) {
  return (
    <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
      <div className="mt-4 flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

function LoadedSummaryCard({ result }: { result: LoadedSummary }) {
  return (
    <div className="mt-5 rounded-md border border-ocean-100 bg-ocean-50 p-4">
      <p className="font-semibold text-ink">{result.title}</p>
      <p className="mt-1 text-sm text-ocean-700">{result.subtitle}</p>
      <ReportSummaryGrid summary={result.summary} />
    </div>
  );
}

function ReportSummaryGrid({ summary }: { summary?: ReportSummary | null }) {
  if (!summary) {
    return <EmptyState title="No attendance records found for the selected period." />;
  }
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-3">
      <Info label="Total records" value={summary.total_records} />
      <Info label="Absent" value={summary.absent_count} />
      <Info
        label="Attendance rate"
        value={summary.attendance_rate_percentage === null ? "Unavailable" : `${summary.attendance_rate_percentage}%`}
      />
    </div>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-l-2 border-slate-300 bg-white px-3 py-2.5">
      <p className="data-label">{label}</p>
      <div className="data-value font-semibold">{value}</div>
    </div>
  );
}
