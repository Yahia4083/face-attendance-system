import { useState } from "react";
import { createDepartment, listDepartments, setDepartmentActive, updateDepartment } from "../api/departments";
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
import type { Department } from "../types/api";
import { localFormError, parseApiError, type FieldErrors } from "../utils/apiErrors";
import { getErrorMessage } from "../utils/errors";

function validateDepartmentForm(editing: Partial<Department>) {
  const errors: FieldErrors = {};
  const messages: string[] = [];
  const name = String(editing.name ?? "").trim();
  if (!name) {
    errors.name = "Department name is required.";
    messages.push(errors.name);
  } else if (name.length < 2) {
    errors.name = "Department name must be at least 2 characters.";
    messages.push(errors.name);
  } else if (name.length > 100) {
    errors.name = "Department name must be no more than 100 characters.";
    messages.push(errors.name);
  }
  return localFormError(messages, errors);
}

export function DepartmentsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState("");
  const [editing, setEditing] = useState<Partial<Department> | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [statusTarget, setStatusTarget] = useState<Department | null>(null);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const { notify } = useToast();
  const departments = useAsync(() => listDepartments({ search: search || undefined, is_active: active || undefined, page, page_size: 10 }), [search, active, page]);

  function startEdit(item: Partial<Department>) {
    setFieldErrors({});
    setMessages([]);
    setEditing(item);
  }

  async function save() {
    if (!editing) return;
    const localErrors = validateDepartmentForm(editing);
    if (localErrors.messages.length) {
      setFieldErrors(localErrors.fieldErrors);
      setMessages(localErrors.messages);
      return;
    }

    setSaving(true);
    setFieldErrors({});
    setMessages([]);
    try {
      const payload = { name: String(editing.name).trim(), description: editing.description?.trim() || null };
      if (editing.id) {
        await updateDepartment(editing.id, payload);
      } else {
        await createDepartment(payload);
      }
      notify("Department saved.", "success");
      setEditing(null);
      departments.refresh();
    } catch (err) {
      const parsed = parseApiError(err);
      setFieldErrors(parsed.fieldErrors);
      setMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setSaving(false);
    }
  }

  async function toggle() {
    if (!statusTarget) return;
    setUpdatingStatus(true);
    try {
      await setDepartmentActive(statusTarget.id, !statusTarget.is_active);
      notify("Department status updated.", "success");
      setStatusTarget(null);
      departments.refresh();
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setUpdatingStatus(false);
    }
  }

  const formIsValid = editing ? !validateDepartmentForm(editing).messages.length : false;

  return (
    <div className="page-stack">
      <PageHeader
        title="Departments"
        description="Create and maintain the departments used to organize employees and attendance reporting."
        action={<Button onClick={() => startEdit({ name: "", description: "" })}>Create department</Button>}
      />
      <Card>
        <SectionHeader title="Find departments" description="Search by name or narrow the list by account status." />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Search"><input className={inputClass} value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} placeholder="Search by department name" /></Field>
          <Field label="Status">
            <select className={inputClass} value={active} onChange={(e) => { setPage(1); setActive(e.target.value); }}>
              <option value="">Any</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </Field>
        </div>
      </Card>
      <Card>
        {departments.loading ? <LoadingState /> : departments.error ? <ErrorState message={departments.error} /> : (
          <>
            <DataTable rowKey={(row) => row.id} rows={departments.data?.items ?? []} emptyTitle="No departments match your filters" empty="Try changing the search term or status filter." columns={[
              { header: "Name", render: (row) => <span className="font-semibold">{row.name}</span> },
              { header: "Description", render: (row) => row.description ?? "No description" },
              { header: "Status", render: (row) => <Badge value={row.is_active} /> },
              { header: "Actions", render: (row) => <div className="flex flex-wrap justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => startEdit(row)}>Edit</Button><Button size="sm" variant={row.is_active ? "danger" : "secondary"} onClick={() => setStatusTarget(row)}>{row.is_active ? "Deactivate" : "Activate"}</Button></div>, className: "text-right" },
            ]} />
            <Pagination page={page} pageSize={departments.data?.page_size ?? 10} total={departments.data?.total ?? 0} onPageChange={setPage} />
          </>
        )}
      </Card>
      <Modal open={Boolean(editing)} title={editing?.id ? "Edit department" : "Create department"} description="Use a clear department name that administrators and employees will recognize." onClose={() => setEditing(null)} footer={<div className="action-row"><Button variant="secondary" onClick={() => setEditing(null)} disabled={saving}>Cancel</Button><Button onClick={save} disabled={!formIsValid} loading={saving} loadingLabel="Saving...">Save department</Button></div>}>
        {editing ? (
          <div className="space-y-4">
            <FormErrorSummary messages={messages} />
            <Field label="Department name" required error={fieldErrors.name}>
              <input className={inputClass} value={editing.name ?? ""} onChange={(e) => { setEditing({ ...editing, name: e.target.value }); setFieldErrors((current) => ({ ...current, name: "" })); }} />
            </Field>
            <Field label="Description">
              <textarea className={inputClass} rows={4} value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            </Field>
          </div>
        ) : null}
      </Modal>
      <ConfirmationDialog
        open={Boolean(statusTarget)}
        title={statusTarget?.is_active ? "Deactivate department?" : "Activate department?"}
        description={statusTarget?.is_active ? `${statusTarget.name} will no longer be available for active workforce operations.` : `${statusTarget?.name ?? "This department"} will become available for active workforce operations.`}
        confirmLabel={statusTarget?.is_active ? "Deactivate" : "Activate"}
        tone={statusTarget?.is_active ? "danger" : "primary"}
        loading={updatingStatus}
        onClose={() => setStatusTarget(null)}
        onConfirm={toggle}
      />
    </div>
  );
}
