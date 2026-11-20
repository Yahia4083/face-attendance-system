import { useState } from "react";
import { approveJustification, approveOvertime, listJustificationRequests, listOvertimeRequests, rejectJustification, rejectOvertime } from "../api/requests";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { Field, FormErrorSummary, inputClass } from "../components/common/Form";
import { Modal } from "../components/common/Modal";
import { PageHeader } from "../components/common/PageHeader";
import { ErrorState, LoadingState } from "../components/common/State";
import { DataTable } from "../components/common/Table";
import { useToast } from "../components/common/Toast";
import { useAsync } from "../hooks/useAsync";
import type { JustificationRequest, OvertimeRequest } from "../types/api";
import { localFormError, parseApiError, type FieldErrors } from "../utils/apiErrors";
import { formatDateTime } from "../utils/dateTime";
import { formatEnumLabel } from "../utils/formatters";

function justificationAdminNote(row: JustificationRequest) {
  if (row.status === "PENDING") return "Not reviewed yet";
  return row.reviewer_note?.trim() || "No admin note provided";
}

export function RequestsPage() {
  const [tab, setTab] = useState<"JUSTIFICATION" | "OVERTIME">("JUSTIFICATION");
  const [status, setStatus] = useState("PENDING");
  const [reviewing, setReviewing] = useState<{ type: "JUSTIFICATION"; item: JustificationRequest } | { type: "OVERTIME"; item: OvertimeRequest } | null>(null);
  const [note, setNote] = useState("");
  const [approvedMinutes, setApprovedMinutes] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const { notify } = useToast();

  const justifications = useAsync(() => listJustificationRequests({ status: status || undefined, page: 1, page_size: 100 }), [status]);
  const overtime = useAsync(() => listOvertimeRequests({ status: status || undefined, page: 1, page_size: 100 }), [status]);

  function beginReview(item: JustificationRequest | OvertimeRequest, type: "JUSTIFICATION" | "OVERTIME") {
    // Opens the admin review modal for the selected request.
    setReviewing(type === "JUSTIFICATION" ? { type, item: item as JustificationRequest } : { type, item: item as OvertimeRequest });
    setNote("");
    setApprovedMinutes(type === "OVERTIME" ? String((item as OvertimeRequest).requested_minutes) : "");
    setFieldErrors({});
    setMessages([]);
  }

  function validateReview(action: "approve" | "reject") {
    const errors: FieldErrors = {};
    const items: string[] = [];
    if (reviewing?.type === "OVERTIME" && action === "approve") {
      // Validates approved overtime minutes before submission.
      const approved = Number(approvedMinutes);
      if (!Number.isInteger(approved) || approved <= 0) {
        errors.approved_minutes = "Approved minutes must be greater than zero.";
        items.push(errors.approved_minutes);
      } else if (approved > reviewing.item.requested_minutes) {
        errors.approved_minutes = "Approved minutes cannot exceed the requested minutes.";
        items.push(errors.approved_minutes);
      } else if (approved > reviewing.item.eligible_minutes_at_submission) {
        errors.approved_minutes = "Approved minutes cannot exceed the eligible overtime minutes recorded at submission.";
        items.push(errors.approved_minutes);
      }
    }
    return localFormError(items, errors);
  }

  async function review(action: "approve" | "reject") {
    if (!reviewing) return;
    const localErrors = validateReview(action);
    if (localErrors.messages.length) {
      setFieldErrors(localErrors.fieldErrors);
      setMessages(localErrors.messages);
      return;
    }

    setSubmitting(true);
    setFieldErrors({});
    setMessages([]);
    try {
      if (reviewing.type === "JUSTIFICATION") {
        // Submits the admin decision for a justification request.
        await (action === "approve" ? approveJustification(reviewing.item.id, note.trim() || undefined) : rejectJustification(reviewing.item.id, note.trim() || undefined));
        justifications.refresh();
      } else {
        // Submits the admin decision for an overtime request.
        await (action === "approve"
          ? approveOvertime(reviewing.item.id, { approved_minutes: Number(approvedMinutes), reviewer_note: note.trim() || undefined })
          : rejectOvertime(reviewing.item.id, note.trim() || undefined));
        overtime.refresh();
      }
      notify(`Request ${action === "approve" ? "approved" : "rejected"}.`, "success");
      setReviewing(null);
      setNote("");
      setApprovedMinutes("");
    } catch (err) {
      const parsed = parseApiError(err);
      setFieldErrors(parsed.fieldErrors);
      setMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader title="Requests" description="Review employee attendance justifications and overtime requests with a consistent, auditable decision workflow." />
      <Card>
        <SectionHeader title="Request queue" description="Choose a request category and status to refine the queue." />
        <div className="flex flex-wrap items-end gap-3">
          <Button aria-pressed={tab === "JUSTIFICATION"} variant={tab === "JUSTIFICATION" ? "primary" : "secondary"} onClick={() => setTab("JUSTIFICATION")}>Justifications</Button>
          <Button aria-pressed={tab === "OVERTIME"} variant={tab === "OVERTIME" ? "primary" : "secondary"} onClick={() => setTab("OVERTIME")}>Overtime</Button>
          <Field label="Status">
            <select className={inputClass} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </Field>
        </div>
      </Card>
      <Card>
        {tab === "JUSTIFICATION" ? (
          justifications.loading ? <LoadingState /> : justifications.error ? <ErrorState message={justifications.error} /> : (
            <DataTable<JustificationRequest>
              rowKey={(row) => row.id}
              rows={justifications.data?.items ?? []}
              emptyTitle="No justification requests match this view"
              empty="Try changing the status filter or check again after employees submit requests."
              columns={[
                { header: "Request ID", render: (row) => `#${row.id}` },
                { header: "Attendance Record", render: (row) => `Record #${row.attendance_record_id}` },
                { header: "Employee", render: (row) => row.employee_name ?? `Employee ${row.employee_id}` },
                { header: "Type", render: (row) => formatEnumLabel(row.request_type) },
                { header: "Status", render: (row) => <Badge value={row.status} label={formatEnumLabel(String(row.status))} /> },
                { header: "Submitted", render: (row) => formatDateTime(row.created_at) },
                { header: "Admin Note", render: (row) => justificationAdminNote(row) },
                { header: "Actions", render: (row) => <div className="flex justify-end">{row.status === "PENDING" ? <Button size="sm" variant="secondary" onClick={() => beginReview(row, "JUSTIFICATION")}>Review</Button> : <span className="text-slate-500">Reviewed</span>}</div>, className: "text-right" },
              ]}
            />
          )
        ) : (
          overtime.loading ? <LoadingState /> : overtime.error ? <ErrorState message={overtime.error} /> : (
          <DataTable<OvertimeRequest>
            rowKey={(row) => row.id}
            rows={overtime.data?.items ?? []}
            emptyTitle="No overtime requests match this view"
            empty="Try changing the status filter or check again after employees submit requests."
            columns={[
              { header: "Employee", render: (row) => row.employee_name ?? `Employee ${row.employee_id}` },
              { header: "Attendance", render: (row) => `#${row.attendance_record_id}` },
              { header: "Requested", render: (row) => `${row.requested_minutes} min` },
              { header: "Status", render: (row) => <Badge value={row.status} /> },
              { header: "Created", render: (row) => formatDateTime(row.created_at) },
              { header: "Actions", render: (row) => <div className="flex justify-end">{row.status === "PENDING" ? <Button size="sm" variant="secondary" onClick={() => beginReview(row, "OVERTIME")}>Review</Button> : <span className="text-slate-500">Reviewed</span>}</div>, className: "text-right" },
            ]}
          />
          )
        )}
      </Card>
      <Modal open={Boolean(reviewing)} title="Review request" description="Review the employee's explanation and record an auditable decision." onClose={() => setReviewing(null)} footer={<div className="action-row"><Button variant="secondary" onClick={() => setReviewing(null)} disabled={submitting}>Cancel</Button><Button variant="danger" onClick={() => review("reject")} disabled={submitting}>Reject</Button><Button onClick={() => review("approve")} loading={submitting} loadingLabel="Submitting...">Approve</Button></div>}>
        {reviewing ? (
          <div className="space-y-4">
            <FormErrorSummary messages={messages} />
            <div className="rounded-md bg-slate-50 p-4 text-sm">
              <p className="font-semibold text-ink">{reviewing.item.employee_name}</p>
              <p className="mt-1 text-slate-600">{reviewing.item.reason}</p>
            </div>
            {reviewing.type === "OVERTIME" ? <Field label="Approved minutes" required error={fieldErrors.approved_minutes} hint={`Requested: ${reviewing.item.requested_minutes} min. Eligible at submission: ${reviewing.item.eligible_minutes_at_submission} min.`}><input className={inputClass} type="number" value={approvedMinutes} onChange={(e) => { setApprovedMinutes(e.target.value); setFieldErrors((current) => ({ ...current, approved_minutes: "" })); }} /></Field> : null}
            <Field label="Reviewer note" error={fieldErrors.reviewer_note} hint="Optional but recommended for audit clarity."><textarea className={inputClass} rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
