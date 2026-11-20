import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createAttendanceCorrection,
  getAttendanceRecord,
  listAttendance,
  listAttendanceCorrections,
  processDailyAttendance,
} from "../api/attendance";
import { listDepartments } from "../api/departments";
import { getEmployee, getEmployeeByNumber } from "../api/employees";
import { getSystemSetting } from "../api/settings";
import { Alert } from "../components/common/Alert";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { ConfirmationDialog } from "../components/common/ConfirmationDialog";
import { Field, FormErrorSummary, inputClass } from "../components/common/Form";
import { Modal } from "../components/common/Modal";
import { PageHeader } from "../components/common/PageHeader";
import { Pagination } from "../components/common/Pagination";
import { ErrorState, LoadingState } from "../components/common/State";
import { DataTable } from "../components/common/Table";
import { useToast } from "../components/common/Toast";
import { useAsync } from "../hooks/useAsync";
import type {
  AttendanceCorrection,
  AttendanceRecord,
  Employee,
  ProcessDailyAttendanceResult,
} from "../types/api";
import { localFormError, parseApiError, type FieldErrors } from "../utils/apiErrors";
import { formatDate, formatDateTime, formatIsoDatePreview, todayIsoDate } from "../utils/dateTime";
import { getErrorMessage } from "../utils/errors";
import { formatEnumLabel as statusLabel } from "../utils/formatters";

const statuses = ["", "PRESENT", "LATE", "EARLY_DEPARTURE", "MISSING_CHECKOUT", "ABSENT", "UNSCHEDULED"];

type FilterKey =
  | "date_from"
  | "date_to"
  | "employee_number"
  | "employee_id"
  | "department_id"
  | "status"
  | "is_late"
  | "is_early_departure"
  | "is_missing_checkout"
  | "is_unscheduled";

type AttendanceFilters = Record<FilterKey, string>;

const emptyFilters: AttendanceFilters = {
  date_from: "",
  date_to: "",
  employee_number: "",
  employee_id: "",
  department_id: "",
  status: "",
  is_late: "",
  is_early_departure: "",
  is_missing_checkout: "",
  is_unscheduled: "",
};

const advancedFilters = [
  { key: "is_late" as const, label: "Late status" },
  { key: "is_early_departure" as const, label: "Early departure" },
  { key: "is_missing_checkout" as const, label: "Missing checkout" },
  { key: "is_unscheduled" as const, label: "Unscheduled attendance" },
];

function readFilters(params: URLSearchParams): AttendanceFilters {
  return Object.keys(emptyFilters).reduce(
    (result, key) => ({
      ...result,
      [key]: params.get(key) ?? "",
    }),
    { ...emptyFilters },
  );
}

function scheduledDetail(record: AttendanceRecord, value?: string | null): string {
  return record.is_unscheduled ? "Not applicable" : formatDateTime(value);
}

function scheduleLabel(record: AttendanceRecord): string {
  return record.is_unscheduled ? "Unscheduled" : (record.schedule_template_name ?? "Not assigned");
}

function issueMinutes(record: AttendanceRecord, value: number, applies: boolean): string {
  return record.is_unscheduled || !applies ? "Not applicable" : `${value} min`;
}

function missingCheckoutEligibility(record: AttendanceRecord, delayMinutes: number | null) {
  if (
    delayMinutes === null
    || record.is_unscheduled
    || !record.check_in_at
    || record.check_out_at
    || !record.scheduled_end_datetime
  ) {
    return null;
  }
  const scheduledEnd = new Date(record.scheduled_end_datetime);
  if (Number.isNaN(scheduledEnd.getTime())) return null;
  const eligibleAt = new Date(scheduledEnd.getTime() + delayMinutes * 60_000);
  return {
    eligibleAt,
    isEligible: Date.now() >= eligibleAt.getTime(),
  };
}

function validateCorrection(status: string, reason: string) {
  const errors: FieldErrors = {};
  const messages: string[] = [];
  if (!status) {
    errors.corrected_status = "Corrected status is required.";
    messages.push(errors.corrected_status);
  }
  const normalizedReason = reason.trim();
  if (normalizedReason.length < 10 || normalizedReason.length > 1000) {
    errors.reason = "Correction reason must be between 10 and 1000 characters.";
    messages.push(errors.reason);
  }
  return localFormError(messages, errors);
}

function requestParams(filters: AttendanceFilters, page: number): Record<string, unknown> {
  const params: Record<string, unknown> = { page, page_size: 10 };
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== "" && key !== "employee_number") params[key] = value;
  });
  return params;
}

export function AttendanceManagementPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialFilters = useMemo(() => readFilters(searchParams), []);
  const [page, setPage] = useState(() => Math.max(1, Number(searchParams.get("page") || 1)));
  const [draftFilters, setDraftFilters] = useState<AttendanceFilters>(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState<AttendanceFilters>(initialFilters);
  const [advancedOpen, setAdvancedOpen] = useState(
    advancedFilters.some(({ key }) => Boolean(initialFilters[key])),
  );
  const [filterMessages, setFilterMessages] = useState<string[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [employeeLookupLoading, setEmployeeLookupLoading] = useState(false);
  const [employeeLookupMessage, setEmployeeLookupMessage] = useState("");
  const [selected, setSelected] = useState<AttendanceRecord | null>(null);
  const [corrections, setCorrections] = useState<AttendanceCorrection[]>([]);
  const [correctionStatus, setCorrectionStatus] = useState("PRESENT");
  const [correctionReason, setCorrectionReason] = useState("");
  const [correctionErrors, setCorrectionErrors] = useState<FieldErrors>({});
  const [correctionMessages, setCorrectionMessages] = useState<string[]>([]);
  const [savingCorrection, setSavingCorrection] = useState(false);
  const [processingDate, setProcessingDate] = useState(todayIsoDate());
  const [processingResult, setProcessingResult] = useState<ProcessDailyAttendanceResult | null>(null);
  const [pendingAction, setPendingAction] = useState<"CORRECTION" | "PROCESSING" | null>(null);
  const [processing, setProcessing] = useState(false);
  const { notify } = useToast();

  const attendance = useAsync(
    () => listAttendance(requestParams(appliedFilters, page)),
    [page, appliedFilters],
  );
  const departments = useAsync(() => listDepartments({ page: 1, page_size: 100 }), []);
  const processingDelaySetting = useAsync(
    () => getSystemSetting("ATTENDANCE_PROCESSING_DELAY_MINUTES"),
    [],
  );
  const missingCheckoutDelaySetting = useAsync(
    () => getSystemSetting("MISSING_CHECKOUT_DELAY_MINUTES"),
    [],
  );
  const configuredDelay = Number(processingDelaySetting.data?.value);
  const processingDelayMinutes = Number.isFinite(configuredDelay) ? configuredDelay : null;
  const configuredMissingCheckoutDelay = Number(missingCheckoutDelaySetting.data?.value);
  const missingCheckoutDelayMinutes = Number.isFinite(configuredMissingCheckoutDelay)
    ? configuredMissingCheckoutDelay
    : null;
  const selectedMissingCheckoutEligibility = selected
    ? missingCheckoutEligibility(selected, missingCheckoutDelayMinutes)
    : null;

  useEffect(() => {
    let cancelled = false;
    if (!appliedFilters.employee_id) {
      setSelectedEmployee(null);
      return;
    }
    getEmployee(Number(appliedFilters.employee_id))
      .then((employee) => {
        if (!cancelled) setSelectedEmployee(employee);
      })
      .catch(() => {
        if (!cancelled) setSelectedEmployee(null);
      });
    return () => {
      cancelled = true;
    };
  }, [appliedFilters.employee_id]);

  function syncUrl(filters: AttendanceFilters, nextPage: number) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== "") params.set(key, value);
    });
    if (nextPage > 1) params.set("page", String(nextPage));
    setSearchParams(params, { replace: true });
  }

  function updateDraft(key: FilterKey, value: string) {
    setDraftFilters((current) => {
      const next = { ...current, [key]: value };
      if (key === "employee_number") {
        next.employee_id = "";
        setSelectedEmployee(null);
        setEmployeeLookupMessage("");
      }
      if (key === "status" && value === "UNSCHEDULED") {
        next.is_unscheduled = "true";
        next.is_late = "";
        next.is_early_departure = "";
        next.is_missing_checkout = "";
      }
      if (key === "status" && value === "ABSENT") {
        next.is_late = "";
        next.is_early_departure = "";
        next.is_missing_checkout = "";
      }
      if (key === "is_unscheduled" && value === "true") {
        next.is_late = "";
        next.is_early_departure = "";
        next.is_missing_checkout = "";
      }
      if (
        (key === "is_late" || key === "is_early_departure")
        && value === "true"
        && next.is_unscheduled === "true"
      ) {
        next.is_unscheduled = "";
      }
      return next;
    });
    setFilterMessages([]);
  }

  async function resolveEmployeeNumber(employeeNumber = draftFilters.employee_number) {
    const normalized = employeeNumber.trim();
    if (!normalized) {
      setSelectedEmployee(null);
      setEmployeeLookupMessage("Enter an employee number before searching.");
      return null;
    }
    setEmployeeLookupLoading(true);
    setEmployeeLookupMessage("");
    try {
      const match = await getEmployeeByNumber(normalized);
      setSelectedEmployee(match);
      setDraftFilters((current) => ({
        ...current,
        employee_number: match.employee_number,
        employee_id: String(match.id),
      }));
      return match;
    } catch {
      setSelectedEmployee(null);
      setDraftFilters((current) => ({ ...current, employee_id: "" }));
      setEmployeeLookupMessage("No employee found with this employee number.");
      return null;
    } finally {
      setEmployeeLookupLoading(false);
    }
  }

  async function applyFilters() {
    if (
      draftFilters.date_from
      && draftFilters.date_to
      && draftFilters.date_from > draftFilters.date_to
    ) {
      setFilterMessages(["Start date cannot be later than end date."]);
      return;
    }

    let next = { ...draftFilters };
    if (next.employee_number.trim()) {
      const exactSelection = selectedEmployee
        && selectedEmployee.employee_number.toLowerCase() === next.employee_number.trim().toLowerCase()
        ? selectedEmployee
        : await resolveEmployeeNumber(next.employee_number);
      if (!exactSelection) {
        setFilterMessages(["No employee found with this employee number."]);
        return;
      }
      next = {
        ...next,
        employee_number: exactSelection.employee_number,
        employee_id: String(exactSelection.id),
      };
    } else {
      next.employee_id = "";
      setSelectedEmployee(null);
    }

    setDraftFilters(next);
    setAppliedFilters(next);
    setFilterMessages([]);
    setPage(1);
    syncUrl(next, 1);
  }

  function clearFilters() {
    setDraftFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setSelectedEmployee(null);
    setEmployeeLookupMessage("");
    setFilterMessages([]);
    setPage(1);
    setAdvancedOpen(false);
    syncUrl(emptyFilters, 1);
  }

  function removeFilter(key: FilterKey) {
    const next = { ...appliedFilters, [key]: "" };
    if (key === "employee_id" || key === "employee_number") {
      next.employee_id = "";
      next.employee_number = "";
      setSelectedEmployee(null);
    }
    setDraftFilters(next);
    setAppliedFilters(next);
    setPage(1);
    syncUrl(next, 1);
  }

  function changePage(nextPage: number) {
    setPage(nextPage);
    syncUrl(appliedFilters, nextPage);
  }

  const activeFilterChips = useMemo(() => {
    const chips: { key: FilterKey; label: string }[] = [];
    if (appliedFilters.date_from) chips.push({ key: "date_from", label: `From: ${appliedFilters.date_from}` });
    if (appliedFilters.date_to) chips.push({ key: "date_to", label: `To: ${appliedFilters.date_to}` });
    if (appliedFilters.employee_number) chips.push({ key: "employee_number", label: `Employee: ${appliedFilters.employee_number}` });
    if (appliedFilters.department_id) {
      const department = departments.data?.items.find(
        (item) => String(item.id) === appliedFilters.department_id,
      );
      chips.push({ key: "department_id", label: `Department: ${department?.name ?? appliedFilters.department_id}` });
    }
    if (appliedFilters.status) chips.push({ key: "status", label: `Status: ${statusLabel(appliedFilters.status)}` });
    advancedFilters.forEach(({ key, label }) => {
      if (appliedFilters[key]) {
        chips.push({ key, label: `${label}: ${appliedFilters[key] === "true" ? "Yes" : "No"}` });
      }
    });
    return chips;
  }, [appliedFilters, departments.data]);

  async function openDetails(id: number) {
    try {
      const [record, history] = await Promise.all([getAttendanceRecord(id), listAttendanceCorrections(id)]);
      setSelected(record);
      setCorrections(history.items);
      setCorrectionStatus(record.effective_status || record.status);
      setCorrectionReason("");
      setCorrectionErrors({});
      setCorrectionMessages([]);
    } catch (error) {
      notify(getErrorMessage(error), "error");
    }
  }

  async function submitCorrection() {
    if (!selected) return;
    const localErrors = validateCorrection(correctionStatus, correctionReason);
    if (localErrors.messages.length) {
      setCorrectionErrors(localErrors.fieldErrors);
      setCorrectionMessages(localErrors.messages);
      return;
    }

    setSavingCorrection(true);
    setCorrectionErrors({});
    setCorrectionMessages([]);
    try {
      await createAttendanceCorrection(selected.id, {
        corrected_status: correctionStatus,
        reason: correctionReason.trim(),
      });
      notify("Attendance correction recorded.", "success");
      setCorrectionReason("");
      await openDetails(selected.id);
      attendance.refresh();
    } catch (error) {
      const parsed = parseApiError(error);
      setCorrectionErrors(parsed.fieldErrors);
      setCorrectionMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setSavingCorrection(false);
    }
  }

  function requestCorrection() {
    const localErrors = validateCorrection(correctionStatus, correctionReason);
    if (localErrors.messages.length) {
      setCorrectionErrors(localErrors.fieldErrors);
      setCorrectionMessages(localErrors.messages);
      return;
    }
    setPendingAction("CORRECTION");
  }

  async function runProcessing() {
    setProcessing(true);
    setProcessingResult(null);
    try {
      const result = await processDailyAttendance(processingDate);
      setProcessingResult(result);
      notify(
        `Processing completed: ${result.absent_records_created} absent created, ${result.missing_checkout_records_updated} missing checkout updated.`,
        "success",
      );
      attendance.refresh();
      if (selected?.schedule_date === processingDate) await openDetails(selected.id);
    } catch (error) {
      notify(getErrorMessage(error), "error");
    } finally {
      setProcessing(false);
      setPendingAction(null);
    }
  }

  async function confirmPendingAction() {
    if (pendingAction === "CORRECTION") {
      await submitCorrection();
      if (!correctionErrors.reason && !correctionErrors.corrected_status) setPendingAction(null);
    }
    if (pendingAction === "PROCESSING") await runProcessing();
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Attendance Management"
        description="Review and filter camera-generated records, run authorized daily processing, and record auditable administrative corrections."
      />
      <Card>
        <SectionHeader
          title="Filter attendance records"
          description="Choose filters, then apply them when you are ready."
        />
        <FormErrorSummary messages={filterMessages} />
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <Field label="Date from" hint={draftFilters.date_from ? formatIsoDatePreview(draftFilters.date_from) : "Optional start date."}>
            <input className={inputClass} type="date" value={draftFilters.date_from} onChange={(event) => updateDraft("date_from", event.target.value)} />
          </Field>
          <Field label="Date to" hint={draftFilters.date_to ? formatIsoDatePreview(draftFilters.date_to) : "Optional end date."}>
            <input className={inputClass} type="date" value={draftFilters.date_to} onChange={(event) => updateDraft("date_to", event.target.value)} />
          </Field>
          <Field label="Employee number" hint="Searches for an exact employee number.">
            <div className="flex gap-2">
              <input
                className={inputClass}
                value={draftFilters.employee_number}
                onChange={(event) => updateDraft("employee_number", event.target.value)}
                placeholder="Enter employee number, for example EMP001"
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    resolveEmployeeNumber();
                  }
                }}
              />
              <Button variant="secondary" onClick={() => resolveEmployeeNumber()} loading={employeeLookupLoading} loadingLabel="Finding...">
                <Search className="h-4 w-4" />
                Find
              </Button>
            </div>
          </Field>
          <Field label="Department">
            <select className={inputClass} value={draftFilters.department_id} onChange={(event) => updateDraft("department_id", event.target.value)}>
              <option value="">All departments</option>
              {departments.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <Field label="Attendance status">
            <select className={inputClass} value={draftFilters.status} onChange={(event) => updateDraft("status", event.target.value)}>
              {statuses.map((status) => <option key={status || "all"} value={status}>{status ? statusLabel(status) : "All statuses"}</option>)}
            </select>
          </Field>
        </div>

        {employeeLookupMessage ? (
          <p className="mt-3 text-sm font-semibold text-rose-600" role="alert">{employeeLookupMessage}</p>
        ) : null}
        {selectedEmployee ? (
          <div className="mt-4 flex flex-col justify-between gap-3 rounded-md border border-ocean-100 bg-ocean-50 p-4 sm:flex-row sm:items-center">
            <div>
              <p className="font-bold text-ink">{selectedEmployee.full_name}</p>
              <p className="mt-1 text-sm text-ocean-800">
                {selectedEmployee.employee_number} · {selectedEmployee.department_name} · {selectedEmployee.is_active ? "Active" : "Inactive"}
              </p>
            </div>
            <Button variant="secondary" onClick={() => updateDraft("employee_number", "")}>Clear employee</Button>
          </div>
        ) : null}

        <div className="mt-5 border-t border-slate-100 pt-5">
          <Button variant="ghost" onClick={() => setAdvancedOpen((current) => !current)}>
            {advancedOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {advancedOpen ? "Hide advanced filters" : "More filters"}
          </Button>
          {advancedOpen ? (
            <div className="mt-4 rounded-md bg-slate-50 p-4">
              <p className="mb-4 text-sm text-slate-600">
                Advanced filters search the original attendance facts recorded by the system.
              </p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {advancedFilters.map(({ key, label }) => (
                  <Field key={key} label={label}>
                    <select className={inputClass} value={draftFilters[key]} onChange={(event) => updateDraft(key, event.target.value)}>
                      <option value="">Any</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </Field>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <Button onClick={applyFilters} disabled={employeeLookupLoading}>Apply filters</Button>
          <Button variant="secondary" onClick={clearFilters}>Clear filters</Button>
        </div>

        {activeFilterChips.length ? (
          <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4" aria-label="Active filters">
            {activeFilterChips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                onClick={() => removeFilter(chip.key)}
                className="inline-flex items-center gap-2 rounded-full bg-ocean-50 px-3 py-1.5 text-xs font-semibold text-ocean-800 hover:bg-ocean-100"
                title="Remove filter"
              >
                {chip.label}
                <X className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>
        ) : null}
      </Card>

      <Card>
        <SectionHeader
          title="Daily Processing"
          description="The background processor automatically creates eligible Absent and Missing Checkout states. Use this manual action only when you need an immediate recheck."
          action={(
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
              <input className={inputClass} type="date" value={processingDate} onChange={(event) => { setProcessingDate(event.target.value); setProcessingResult(null); }} />
              <Button onClick={() => setPendingAction("PROCESSING")}>Run processing</Button>
            </div>
          )}
        />
        <p className="text-xs text-slate-500">{formatIsoDatePreview(processingDate)}</p>
        <p className="mt-2 text-sm text-slate-600">
          {processingDelayMinutes === null || missingCheckoutDelayMinutes === null
            ? "Loading the configured attendance processing policies..."
            : `Absences become eligible ${processingDelayMinutes} minutes after shift end. Open check-ins receive ${missingCheckoutDelayMinutes} minutes (${missingCheckoutDelayMinutes / 60} hours) for overtime or delayed checkout before Missing Checkout processing.`}
        </p>
        {processingResult ? (
          <div className="mt-4">
            <Alert tone="success" title="Processing result">
              Created {processingResult.absent_records_created} absent record(s), marked {processingResult.missing_checkout_records_updated} missing checkout record(s), and left {processingResult.already_processed_or_unchanged} assignment(s) already processed, unchanged, or not yet eligible.
            </Alert>
          </div>
        ) : null}
      </Card>

      <Card>
        <SectionHeader title="Attendance Records" />
        {attendance.loading ? <LoadingState /> : attendance.error ? <ErrorState message={attendance.error} /> : (
          <>
            <DataTable
              rowKey={(row) => row.id}
              rows={attendance.data?.items ?? []}
              emptyTitle="No attendance records match the selected filters."
              empty="Clear one or more filters, or choose a different date range."
              columns={[
                { header: "Employee", render: (row) => <div><p className="font-semibold">{row.employee_name}</p><p className="text-xs text-slate-500">{row.employee_number}</p></div> },
                { header: "Date", render: (row) => formatDate(row.schedule_date) },
                { header: "Original", render: (row) => <Badge value={row.status} /> },
                { header: "Effective", render: (row) => <Badge value={row.effective_status} /> },
                { header: "In", render: (row) => formatDateTime(row.check_in_at) },
                { header: "Out", render: (row) => formatDateTime(row.check_out_at) },
                { header: "Actions", className: "text-right", render: (row) => <div className="flex justify-end"><Button size="sm" variant="secondary" onClick={() => openDetails(row.id)}>Details</Button></div> },
              ]}
            />
            <Pagination page={page} pageSize={attendance.data?.page_size ?? 10} total={attendance.data?.total ?? 0} onPageChange={changePage} />
          </>
        )}
      </Card>

      <Modal
        open={Boolean(selected)}
        title={selected ? `Attendance #${selected.id}` : "Attendance details"}
        description="Original camera-generated facts remain visible even when an administrative correction exists."
        onClose={() => setSelected(null)}
        footer={<div className="action-row"><Button variant="secondary" onClick={() => setSelected(null)}>Close</Button></div>}
      >
        {selected ? (
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2">
              <Info label="Employee" value={`${selected.employee_name ?? "Unknown"} (${selected.employee_number ?? "N/A"})`} />
              <Info label="Schedule date" value={selected.schedule_date} />
              <Info label="Schedule" value={scheduleLabel(selected)} />
              <Info label="Original factual status" value={<Badge value={selected.status} />} />
              <Info label="Effective admin status" value={<Badge value={selected.effective_status} />} />
              <Info label="Scheduled start" value={scheduledDetail(selected, selected.scheduled_start_datetime)} />
              <Info label="Scheduled end" value={scheduledDetail(selected, selected.scheduled_end_datetime)} />
              <Info label="Actual check-in" value={formatDateTime(selected.check_in_at)} />
              <Info label="Actual check-out" value={formatDateTime(selected.check_out_at)} />
              <Info label="Late minutes" value={issueMinutes(selected, selected.late_minutes, selected.is_late)} />
              <Info label="Early departure minutes" value={issueMinutes(selected, selected.early_departure_minutes, selected.is_early_departure)} />
            </div>
            {selectedMissingCheckoutEligibility ? (
              <Alert
                tone={selected.is_missing_checkout || selectedMissingCheckoutEligibility.isEligible ? "warning" : "info"}
                title="Missing checkout processing"
              >
                {selected.is_missing_checkout
                  ? "This attendance record has already been marked as Missing Checkout."
                  : selectedMissingCheckoutEligibility.isEligible
                    ? "This open check-in has reached its cutoff and will be marked automatically during the next processing cycle."
                    : `This open check-in becomes eligible at ${formatDateTime(selectedMissingCheckoutEligibility.eligibleAt.toISOString())}. The configured overtime and delayed-checkout window is ${missingCheckoutDelayMinutes} minutes after scheduled end.`}
              </Alert>
            ) : null}
            <div className="rounded-md border border-slate-200 p-4">
              <h3 className="font-semibold text-ink">Administrative correction</h3>
              <p className="mt-1 text-sm text-slate-500">This does not fabricate camera attendance timestamps or erase the original status.</p>
              <div className="mt-4 grid gap-3">
                <FormErrorSummary messages={correctionMessages} />
                <Field label="Corrected status" required error={correctionErrors.corrected_status}>
                  <select className={inputClass} value={correctionStatus} onChange={(event) => { setCorrectionStatus(event.target.value); setCorrectionErrors((current) => ({ ...current, corrected_status: "" })); }}>
                    {statuses.filter(Boolean).map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
                  </select>
                </Field>
                <Field label="Correction reason" required error={correctionErrors.reason} hint="Required for auditability. Explain why the administrative correction is being recorded.">
                  <textarea className={inputClass} rows={3} value={correctionReason} onChange={(event) => { setCorrectionReason(event.target.value); setCorrectionErrors((current) => ({ ...current, reason: "" })); }} placeholder="Example: Verified administrative documentation confirms the corrected status." />
                </Field>
                <Button onClick={requestCorrection} disabled={savingCorrection}>Save audited correction</Button>
              </div>
            </div>
            <div>
              <h3 className="font-semibold text-ink">Correction history</h3>
              <div className="mt-3 space-y-2">
                {corrections.length === 0 ? <p className="text-sm text-slate-500">No corrections recorded.</p> : corrections.map((item) => (
                  <div className="rounded-md bg-slate-50 p-3 text-sm" key={item.id}>
                    <p><Badge value={item.original_status} /> to <Badge value={item.corrected_status} /></p>
                    <p className="mt-2 text-slate-600">{item.reason}</p>
                    <p className="mt-1 text-xs text-slate-500">By user {item.corrected_by_user_id} - {formatDateTime(item.corrected_at)}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
      <ConfirmationDialog
        open={Boolean(pendingAction)}
        title={pendingAction === "CORRECTION" ? "Record administrative correction?" : "Run daily attendance processing?"}
        description={pendingAction === "CORRECTION" ? "The correction will be audit logged while original camera-generated facts and timestamps remain preserved." : `Run an immediate manual recheck of eligible completed shifts for ${formatIsoDatePreview(processingDate).replace("Selected: ", "")}. Automatic background processing will continue normally.`}
        confirmLabel={pendingAction === "CORRECTION" ? "Record correction" : "Run processing"}
        tone={pendingAction === "CORRECTION" ? "primary" : "primary"}
        loading={savingCorrection || processing}
        onClose={() => {
          if (savingCorrection || processing) return;
          setPendingAction(null);
        }}
        onConfirm={confirmPendingAction}
      />
    </div>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-l-2 border-slate-300 bg-slate-50 px-3 py-2.5">
      <p className="data-label">{label}</p>
      <div className="data-value font-semibold">{value}</div>
    </div>
  );
}
