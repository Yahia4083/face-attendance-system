import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge } from "../../components/common/Badge";
import { Alert } from "../../components/common/Alert";
import { Button } from "../../components/common/Button";
import { Card, SectionHeader } from "../../components/common/Card";
import { Field, FormErrorSummary, inputClass } from "../../components/common/Form";
import { PageHeader } from "../../components/common/PageHeader";
import { Pagination } from "../../components/common/Pagination";
import { ErrorState, LoadingState } from "../../components/common/State";
import { DataTable } from "../../components/common/Table";
import { useToast } from "../../components/common/Toast";
import {
  createMyJustificationRequest,
  createMyOvertimeRequest,
  listMyAttendance,
  listMyJustificationRequests,
  listMyOvertimeRequests,
} from "../../api/employeeSelfService";
import { useAsync } from "../../hooks/useAsync";
import type { AttendanceRecord, JustificationRequest, OvertimeRequest } from "../../types/api";
import { formatDate, formatDateTime } from "../../utils/dateTime";
import { formatEnumLabel } from "../../utils/formatters";
import { canRequestAttendanceReview, inferredJustificationType } from "../../utils/employeeRequestShortcuts";
import { parseApiError, type ParsedApiError } from "../../utils/apiErrors";

type RequestKind = "JUSTIFICATION" | "OVERTIME";

const justificationTypes = ["LATE", "EARLY_DEPARTURE", "MISSING_CHECKOUT"];
const statuses = ["", "PENDING", "APPROVED", "REJECTED"];

function adminNoteForRequest(row: JustificationRequest | OvertimeRequest) {
  if (row.status === "PENDING") return "Not reviewed yet";
  return row.reviewer_note?.trim() || "No admin note provided";
}

function SelectedRecordSummary({
  record,
  attendanceRecordId,
}: {
  record?: AttendanceRecord;
  attendanceRecordId: string;
}) {
  // Renders a selected-record summary when full record details are unavailable.
  if (!record) {
    return (
      <div className="rounded-md border border-ocean-100 bg-ocean-50 p-4 text-sm text-ocean-800">
        <p className="font-semibold">Selected attendance record: #{attendanceRecordId}</p>
        <p className="mt-1">Details are not in the recent records list, but the backend will still verify ownership and eligibility when you submit.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-ocean-100 bg-ocean-50 p-4 text-sm text-ocean-800">
      <p className="font-semibold">Selected attendance record</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <span>Date: {formatDate(record.schedule_date)}</span>
        <span>Status: {formatEnumLabel(record.effective_status || record.status)}</span>
        <span>Check-in: {formatDateTime(record.check_in_at)}</span>
        <span>Check-out: {formatDateTime(record.check_out_at)}</span>
      </div>
    </div>
  );
}

export function MyRequestsPage() {
  const { notify } = useToast();
  const [searchParams] = useSearchParams();
  // Reads preselected attendance request values from the URL.
  const preselectedAttendanceId = searchParams.get("attendanceRecordId") ?? "";
  const preselectedRequestType = searchParams.get("requestType") ?? "";
  const [kind, setKind] = useState<RequestKind>("JUSTIFICATION");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [form, setForm] = useState({
    attendance_record_id: "",
    request_type: "LATE",
    requested_minutes: "30",
    reason: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<ParsedApiError | null>(null);

  const requestParams = useMemo(() => ({ status: status || undefined, page, page_size: 10 }), [status, page]);
  const justifications = useAsync(() => listMyJustificationRequests(requestParams), [JSON.stringify(requestParams)]);
  const overtime = useAsync(() => listMyOvertimeRequests(requestParams), [JSON.stringify(requestParams)]);
  const attendance = useAsync(() => listMyAttendance({ page: 1, page_size: 100 }), []);

  const rows = kind === "JUSTIFICATION" ? (justifications.data?.items ?? []) : (overtime.data?.items ?? []);
  const total = kind === "JUSTIFICATION" ? (justifications.data?.total ?? 0) : (overtime.data?.total ?? 0);
  const pageSize = kind === "JUSTIFICATION" ? (justifications.data?.page_size ?? 10) : (overtime.data?.page_size ?? 10);
  const loading = kind === "JUSTIFICATION" ? justifications.loading : overtime.loading;
  const error = kind === "JUSTIFICATION" ? justifications.error : overtime.error;
  const attendanceRecords = attendance.data?.items ?? [];
  // Builds the selectable attendance-record options for the current request kind.
  const attendanceOptions = attendanceRecords.filter((record) => (kind === "JUSTIFICATION" ? canRequestAttendanceReview(record) : true));
  const selectedRecord = attendanceRecords.find((record) => String(record.id) === form.attendance_record_id);
  const selectedRecordMissingFromOptions =
    form.attendance_record_id && !attendanceOptions.some((record) => String(record.id) === form.attendance_record_id);
  const selectedRecordHasJustification = Boolean(
    selectedRecord?.latest_justification_status || selectedRecord?.has_pending_justification,
  );

  useEffect(() => {
    if (!preselectedAttendanceId) return;
    // Applies the preselected attendance record from the URL.
    setKind("JUSTIFICATION");
    setForm((current) => ({
      ...current,
      attendance_record_id: preselectedAttendanceId,
      request_type: justificationTypes.includes(preselectedRequestType) ? preselectedRequestType : current.request_type,
    }));
  }, [preselectedAttendanceId, preselectedRequestType]);

  useEffect(() => {
    if (kind !== "JUSTIFICATION" || !selectedRecord) return;
    // Updates the justification type from the selected attendance record.
    const inferred = inferredJustificationType(selectedRecord);
    if (inferred) {
      setForm((current) => ({ ...current, request_type: inferred }));
    }
  }, [kind, selectedRecord?.id]);

  function selectAttendanceRecord(recordId: string) {
    const record = attendanceRecords.find((item) => String(item.id) === recordId);
    const inferred = inferredJustificationType(record);
    setForm((current) => ({
      ...current,
      attendance_record_id: recordId,
      request_type: kind === "JUSTIFICATION" && inferred ? inferred : current.request_type,
    }));
  }

  async function refreshLists() {
    // Refreshes request and attendance lists after submission.
    await Promise.all([justifications.refresh(), overtime.refresh(), attendance.refresh()]);
  }

  async function submitRequest(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      const attendanceId = Number(form.attendance_record_id);
      if (!attendanceId) {
        setFormError({
          summary: "Please select an attendance record.",
          messages: ["Please select an attendance record."],
          fieldErrors: { attendance_record_id: "Please select an attendance record." },
        });
        return;
      }
      if (kind === "JUSTIFICATION" && selectedRecordHasJustification) {
        // Blocks duplicate justification submission for the selected record.
        setFormError({
          summary: "A justification request has already been submitted for this record.",
          messages: ["A justification request has already been submitted for this record."],
          fieldErrors: {},
        });
        return;
      }

      if (kind === "JUSTIFICATION") {
        // Submits the employee justification request.
        await createMyJustificationRequest(attendanceId, {
          request_type: form.request_type,
          reason: form.reason,
        });
        notify("Justification request submitted successfully.", "success");
      } else {
        await createMyOvertimeRequest(attendanceId, {
          requested_minutes: Number(form.requested_minutes),
          reason: form.reason,
        });
        notify("Overtime request submitted successfully.", "success");
      }
      setForm((current) => ({ ...current, reason: "" }));
      await refreshLists();
    } catch (err) {
      setFormError(parseApiError(err, { attendance_record_id: "Attendance record", request_type: "Request type", requested_minutes: "Requested minutes" }));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader title="My Requests" description="Submit eligible attendance justification or overtime requests for your own records only." />

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <form onSubmit={submitRequest}>
          <Card>
          <SectionHeader title="Submit a request" description="Select a camera-generated attendance record, then explain what needs review." />
          <div className="space-y-4">
            <Field label="Request category" required>
              <select className={inputClass} value={kind} onChange={(event) => setKind(event.target.value as RequestKind)}>
                <option value="JUSTIFICATION">Attendance justification</option>
                <option value="OVERTIME">Overtime request</option>
              </select>
            </Field>
            <Field
              label="Attendance record"
              required
              error={formError?.fieldErrors.attendance_record_id}
              hint={
                kind === "JUSTIFICATION"
                  ? "Only records with lateness, early departure, or missing checkout issues are listed."
                  : "Select the attendance record related to the overtime request."
              }
            >
              <select
                className={inputClass}
                value={form.attendance_record_id}
                onChange={(event) => selectAttendanceRecord(event.target.value)}
              >
                <option value="">Select one of your recent records</option>
                {selectedRecordMissingFromOptions ? (
                  <option value={form.attendance_record_id}>Selected record #{form.attendance_record_id}</option>
                ) : null}
                {attendanceOptions.map((record) => (
                  <option key={record.id} value={record.id}>
                    #{record.id} - {formatDate(record.schedule_date)} - {formatEnumLabel(record.effective_status || record.status)}
                  </option>
                ))}
              </select>
            </Field>
            {kind === "JUSTIFICATION" && !attendance.loading && attendanceOptions.length === 0 ? (
              <Alert tone="info">No eligible attendance records were found for a new request.</Alert>
            ) : null}
            {form.attendance_record_id ? (
              <SelectedRecordSummary record={selectedRecord} attendanceRecordId={form.attendance_record_id} />
            ) : null}
            {selectedRecordHasJustification ? (
              <Alert tone="warning" title="Request already submitted">
                A justification request has already been submitted for this record. Current status:{" "}
                {formatEnumLabel(String(selectedRecord?.latest_justification_status ?? "PENDING"))}.
              </Alert>
            ) : null}
            {kind === "JUSTIFICATION" ? (
              <Field label="Justification type" required error={formError?.fieldErrors.request_type}>
                <select
                  className={inputClass}
                  value={form.request_type}
                  onChange={(event) => setForm((current) => ({ ...current, request_type: event.target.value }))}
                >
                  {justificationTypes.map((type) => (
                    <option key={type} value={type}>
                      {formatEnumLabel(type)}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <Field label="Requested minutes" required error={formError?.fieldErrors.requested_minutes}>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  value={form.requested_minutes}
                  onChange={(event) => setForm((current) => ({ ...current, requested_minutes: event.target.value }))}
                />
              </Field>
            )}
            <Field label="Reason" required error={formError?.fieldErrors.reason} hint="Explain the situation clearly for administrative review.">
              <textarea
                className={`${inputClass} min-h-28`}
                value={form.reason}
                onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))}
              />
            </Field>
            {formError ? <FormErrorSummary messages={formError.messages} /> : null}
            <Button type="submit" disabled={!form.reason.trim() || selectedRecordHasJustification} loading={submitting} loadingLabel="Submitting...">
              Submit request
            </Button>
          </div>
          </Card>
        </form>

        <Card>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-display text-xl font-bold text-ink">Request history</h2>
            <div className="flex gap-2">
              <Button size="sm" aria-pressed={kind === "JUSTIFICATION"} variant={kind === "JUSTIFICATION" ? "primary" : "secondary"} onClick={() => setKind("JUSTIFICATION")}>
                Justifications
              </Button>
              <Button size="sm" aria-pressed={kind === "OVERTIME"} variant={kind === "OVERTIME" ? "primary" : "secondary"} onClick={() => setKind("OVERTIME")}>
                Overtime
              </Button>
            </div>
          </div>
          <div className="mt-4 max-w-xs">
            <Field label="Status filter">
              <select
                className={inputClass}
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
              >
                {statuses.map((item) => (
                  <option key={item || "all"} value={item}>
                    {item ? item : "All statuses"}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="mt-5">
            {loading ? (
              <LoadingState label="Loading requests..." />
            ) : error ? (
              <ErrorState message={error} />
            ) : kind === "JUSTIFICATION" ? (
              <DataTable<JustificationRequest>
                rowKey={(row) => row.id}
                rows={rows as JustificationRequest[]}
                emptyTitle="No justification requests found"
                empty="Submit a request when an eligible attendance record needs review."
                columns={[
                  { header: "Request ID", render: (row) => `#${row.id}` },
                  { header: "Attendance Record", render: (row) => `Record #${row.attendance_record_id}` },
                  { header: "Type", render: (row) => formatEnumLabel(row.request_type) },
                  { header: "Status", render: (row) => <Badge value={row.status} label={formatEnumLabel(String(row.status))} /> },
                  { header: "Submitted", render: (row) => formatDateTime(row.created_at) },
                  { header: "Admin Note", render: (row) => adminNoteForRequest(row) },
                ]}
              />
            ) : (
              <DataTable<OvertimeRequest>
                rowKey={(row) => row.id}
                rows={rows as OvertimeRequest[]}
                emptyTitle="No overtime requests found"
                empty="Submit an overtime request when a completed scheduled record is eligible."
                columns={[
                  { header: "Request ID", render: (row) => `#${row.id}` },
                  { header: "Attendance Record", render: (row) => `Record #${row.attendance_record_id}` },
                  { header: "Requested", render: (row) => `${row.requested_minutes} min` },
                  { header: "Approved", render: (row) => (row.approved_minutes == null ? "Not approved" : `${row.approved_minutes} min`) },
                  { header: "Status", render: (row) => <Badge value={row.status} label={formatEnumLabel(String(row.status))} /> },
                  { header: "Submitted", render: (row) => formatDateTime(row.created_at) },
                  { header: "Admin Note", render: (row) => adminNoteForRequest(row) },
                ]}
              />
            )}
            <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
          </div>
        </Card>
      </section>
      <p className="text-xs text-slate-500">
        Recent attendance records are loaded only to help select a related record. This page does not modify attendance facts.
      </p>
    </div>
  );
}
