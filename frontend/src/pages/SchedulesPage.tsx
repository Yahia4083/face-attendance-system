import { useState } from "react";
import { createScheduleTemplate, listScheduleTemplates, setScheduleTemplateActive } from "../api/schedules";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { ConfirmationDialog } from "../components/common/ConfirmationDialog";
import { Field, FormErrorSummary, inputClass } from "../components/common/Form";
import { Modal } from "../components/common/Modal";
import { PageHeader } from "../components/common/PageHeader";
import { ErrorState, LoadingState } from "../components/common/State";
import { DataTable } from "../components/common/Table";
import { TimePicker } from "../components/common/TimePicker";
import { useToast } from "../components/common/Toast";
import { useAsync } from "../hooks/useAsync";
import type { ScheduleTemplate } from "../types/api";
import { localFormError, parseApiError, type FieldErrors } from "../utils/apiErrors";
import { getErrorMessage } from "../utils/errors";
import { formatTime } from "../utils/dateTime";

type TemplateForm = Partial<ScheduleTemplate>;

function validateTemplateForm(form: TemplateForm) {
  // Validates the schedule-template form fields.
  const errors: FieldErrors = {};
  const messages: string[] = [];
  const add = (field: string, message: string) => {
    errors[field] = message;
    messages.push(message);
  };

  if (!String(form.name ?? "").trim()) add("name", "Template name is required.");
  else if (String(form.name).trim().length < 2) add("name", "Template name must be at least 2 characters.");
  if (!form.start_time) add("start_time", "Start time is required.");
  if (!form.end_time) add("end_time", "End time is required.");
  if (Number(form.check_in_grace_minutes ?? 0) < 0 || Number(form.check_in_grace_minutes ?? 0) > 120) add("check_in_grace_minutes", "Check-in grace minutes must be between 0 and 120.");
  if (Number(form.early_departure_tolerance_minutes ?? 0) < 0 || Number(form.early_departure_tolerance_minutes ?? 0) > 120) add("early_departure_tolerance_minutes", "Early departure tolerance must be between 0 and 120 minutes.");

  return localFormError(messages, errors);
}

export function SchedulesPage() {
  const { notify } = useToast();
  const [templateForm, setTemplateForm] = useState<TemplateForm | null>(null);
  const [templateErrors, setTemplateErrors] = useState<FieldErrors>({});
  const [templateMessages, setTemplateMessages] = useState<string[]>([]);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [statusTarget, setStatusTarget] = useState<ScheduleTemplate | null>(null);
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const templates = useAsync(() => listScheduleTemplates({ page: 1, page_size: 100 }), []);

  function openTemplateForm() {
    setTemplateErrors({});
    setTemplateMessages([]);
    setTemplateForm({ name: "", start_time: "08:00:00", end_time: "16:00:00", is_overnight: false, check_in_grace_minutes: 10, early_departure_tolerance_minutes: 5 });
  }

  function updateTemplateField<K extends keyof TemplateForm>(field: K, value: TemplateForm[K]) {
    if (!templateForm) return;
    setTemplateForm({ ...templateForm, [field]: value });
    setTemplateErrors((current) => {
      const next = { ...current };
      delete next[String(field)];
      return next;
    });
  }

  async function saveTemplate() {
    if (!templateForm) return;
    // Runs local validation before saving the template.
    const localErrors = validateTemplateForm(templateForm);
    if (localErrors.messages.length) {
      setTemplateErrors(localErrors.fieldErrors);
      setTemplateMessages(localErrors.messages);
      return;
    }

    setSavingTemplate(true);
    setTemplateErrors({});
    setTemplateMessages([]);
    try {
      // Sends the schedule-template payload to the backend.
      await createScheduleTemplate({
        name: String(templateForm.name).trim(),
        description: templateForm.description ? String(templateForm.description).trim() : null,
        start_time: String(templateForm.start_time),
        end_time: String(templateForm.end_time),
        is_overnight: Boolean(templateForm.is_overnight),
        check_in_grace_minutes: Number(templateForm.check_in_grace_minutes ?? 0),
        early_departure_tolerance_minutes: Number(templateForm.early_departure_tolerance_minutes ?? 0),
      });
      notify("Schedule template created.", "success");
      setTemplateForm(null);
      templates.refresh();
    } catch (err) {
      const parsed = parseApiError(err);
      setTemplateErrors(parsed.fieldErrors);
      setTemplateMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setSavingTemplate(false);
    }
  }

  async function toggleTemplate() {
    if (!statusTarget) return;
    setUpdatingStatus(true);
    try {
      // Toggles the selected schedule template status.
      await setScheduleTemplateActive(statusTarget.id, !statusTarget.is_active);
      notify("Template status updated.", "success");
      setStatusTarget(null);
      templates.refresh();
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setUpdatingStatus(false);
    }
  }

  const templateIsValid = templateForm ? !validateTemplateForm(templateForm).messages.length : false;

  return (
    <div className="page-stack">
      <PageHeader
        title="Schedule Templates"
        description="Define reusable daytime and overnight shifts. Employee assignments remain available from the Employees page."
        action={<Button onClick={openTemplateForm}>Create template</Button>}
      />
      <Card>
        <SectionHeader title="Available templates" description="Times are shown in the organization business timezone." />
        {templates.loading ? <LoadingState /> : templates.error ? <ErrorState message={templates.error} /> : (
          <DataTable rowKey={(row) => row.id} rows={templates.data?.items ?? []} emptyTitle="No schedule templates have been created yet" empty="Create a template before assigning work schedules to employees." columns={[
            // Renders schedule-template table columns.
            { header: "Name", render: (row) => <span className="font-semibold">{row.name}</span> },
            { header: "Shift", render: (row) => `${formatTime(row.start_time)} to ${formatTime(row.end_time)}${row.is_overnight ? " next day" : ""}` },
            { header: "Overnight", render: (row) => <Badge value={row.is_overnight} label={row.is_overnight ? "Yes" : "No"} /> },
            { header: "Grace", render: (row) => `${row.check_in_grace_minutes} min` },
            { header: "Early tolerance", render: (row) => `${row.early_departure_tolerance_minutes} min` },
            { header: "Status", render: (row) => <Badge value={row.is_active} /> },
            { header: "Actions", render: (row) => <div className="flex justify-end"><Button size="sm" variant={row.is_active ? "danger" : "secondary"} onClick={() => setStatusTarget(row)}>{row.is_active ? "Deactivate" : "Activate"}</Button></div>, className: "text-right" },
          ]} />
        )}
      </Card>

      <Modal open={Boolean(templateForm)} title="Create schedule template" description="Define the shift window and attendance tolerances used for future records." onClose={() => setTemplateForm(null)} footer={<div className="action-row"><Button variant="secondary" onClick={() => setTemplateForm(null)} disabled={savingTemplate}>Cancel</Button><Button onClick={saveTemplate} disabled={!templateIsValid} loading={savingTemplate} loadingLabel="Saving...">Save template</Button></div>}>
        {templateForm ? (
          <div className="space-y-4">
            <FormErrorSummary messages={templateMessages} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Template name" required error={templateErrors.name}><input className={inputClass} value={templateForm.name ?? ""} onChange={(e) => updateTemplateField("name", e.target.value)} /></Field>
              <Field label="Description"><input className={inputClass} value={templateForm.description ?? ""} onChange={(e) => updateTemplateField("description", e.target.value)} /></Field>
              <TimePicker label="Start time" required error={templateErrors.start_time} value={templateForm.start_time} onChange={(value) => updateTemplateField("start_time", value)} />
              <TimePicker label="End time" required error={templateErrors.end_time} value={templateForm.end_time} onChange={(value) => updateTemplateField("end_time", value)} />
              <Field label="Check-in grace minutes" required error={templateErrors.check_in_grace_minutes}><input className={inputClass} type="number" min="0" max="120" value={templateForm.check_in_grace_minutes ?? 0} onChange={(e) => updateTemplateField("check_in_grace_minutes", Number(e.target.value))} /></Field>
              <Field label="Early departure tolerance" required error={templateErrors.early_departure_tolerance_minutes}><input className={inputClass} type="number" min="0" max="120" value={templateForm.early_departure_tolerance_minutes ?? 0} onChange={(e) => updateTemplateField("early_departure_tolerance_minutes", Number(e.target.value))} /></Field>
              <label className="flex min-h-11 items-center gap-3 rounded-md border border-slate-300 bg-slate-50 px-3 text-sm font-semibold text-slate-700"><input className="h-4 w-4 accent-ocean-600" type="checkbox" checked={Boolean(templateForm.is_overnight)} onChange={(e) => updateTemplateField("is_overnight", e.target.checked)} /> Overnight shift</label>
            </div>
          </div>
        ) : null}
      </Modal>
      <ConfirmationDialog
        open={Boolean(statusTarget)}
        title={statusTarget?.is_active ? "Deactivate schedule template?" : "Activate schedule template?"}
        description={statusTarget?.is_active ? `${statusTarget.name} will no longer be available for new active assignments.` : `${statusTarget?.name ?? "This template"} will become available for schedule assignments.`}
        confirmLabel={statusTarget?.is_active ? "Deactivate" : "Activate"}
        tone={statusTarget?.is_active ? "danger" : "primary"}
        loading={updatingStatus}
        onClose={() => setStatusTarget(null)}
        onConfirm={toggleTemplate}
      />
    </div>
  );
}
