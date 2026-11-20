import { useState } from "react";
import {
  deactivateFaceEnrollment,
  enrollFace,
  getFaceStatus,
  listFaceEmbeddings,
  parseFaceEnrollmentValidationError,
  reEnrollFace,
  type FaceEmbeddingMetadata,
  type FaceImageValidationIssue,
  type FaceStatus,
} from "../api/faceEnrollment";
import {
  createEmployee,
  listEmployees,
  resetEmployeePassword,
  setEmployeeActive,
  updateEmployee,
} from "../api/employees";
import { listDepartments } from "../api/departments";
import { assignEmployeeSchedule, listEmployeeSchedules, listScheduleTemplates } from "../api/schedules";
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
import type { Employee, EmployeeSchedule } from "../types/api";
import { localFormError, parseApiError, type FieldErrors } from "../utils/apiErrors";
import {
  formatDate,
  formatDateTime,
  formatIsoDatePreview,
  formatTime,
  formatWorkingDays,
  libyaWeekdayOptions,
  todayIsoDate,
} from "../utils/dateTime";
import { getErrorMessage } from "../utils/errors";

type EmployeeForm = {
  id?: number;
  email: string;
  password: string;
  full_name: string;
  employee_number: string;
  phone: string;
  position: string;
  department_id: string;
};

const emptyForm: EmployeeForm = {
  email: "",
  password: "",
  full_name: "",
  employee_number: "",
  phone: "",
  position: "",
  department_id: "",
};

type AssignmentForm = {
  schedule_template_id: string;
  effective_from: string;
  effective_to: string;
  no_end_date: boolean;
  working_days: number[];
};

type PasswordResetForm = {
  employee: Employee;
  new_password: string;
  confirm_password: string;
  require_password_change: boolean;
};

type FaceBatchValidationState = {
  total: number;
  invalidImageCount: number;
  errors: FaceImageValidationIssue[];
};

type PendingAction =
  | { type: "PASSWORD_RESET" }
  | { type: "EMPLOYEE_STATUS"; employee: Employee }
  | { type: "FACE_DEACTIVATION" }
  | { type: "SCHEDULE_ASSIGNMENT" };

const defaultAssignment: AssignmentForm = {
  schedule_template_id: "",
  effective_from: todayIsoDate(),
  effective_to: "",
  no_end_date: true,
  // Defines the default working days for a new schedule assignment.
  working_days: [5, 6, 0, 1, 2],
};

function faceFileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function isSupportedFaceImage(file: File) {
  // Checks whether the selected file is a supported face image.
  const allowedTypes = new Set(["image/jpeg", "image/png"]);
  const lowerName = file.name.toLowerCase();
  const allowedExtension = lowerName.endsWith(".jpg") || lowerName.endsWith(".jpeg") || lowerName.endsWith(".png");
  return allowedTypes.has(file.type) && allowedExtension;
}

function formatFileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} bytes`;
}

function validateEmployeeForm(form: EmployeeForm) {
  // Validates the employee create/edit form fields.
  const errors: FieldErrors = {};
  const messages: string[] = [];
  const add = (field: string, message: string) => {
    errors[field] = message;
    messages.push(message);
  };

  if (!form.email.trim()) add("email", "Email address is required.");
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) add("email", "Please enter a valid email address.");

  if (!form.id) {
    if (form.password.length < 6) add("password", "Password must be at least 6 characters.");
    if (!form.employee_number.trim()) add("employee_number", "Employee number is required.");
    else if (form.employee_number.trim().length < 2) add("employee_number", "Employee number must be at least 2 characters.");
  }

  if (!form.full_name.trim()) add("full_name", "Full name is required.");
  else if (form.full_name.trim().length < 2) add("full_name", "Full name must be at least 2 characters.");
  if (!form.department_id || Number(form.department_id) <= 0) add("department_id", "Please select a department.");
  if (form.position.trim() && form.position.trim().length < 2) add("position", "Position must be at least 2 characters.");

  return localFormError(messages, errors);
}

function validatePasswordReset(form: PasswordResetForm) {
  const errors: FieldErrors = {};
  const messages: string[] = [];
  const add = (field: string, message: string) => {
    errors[field] = message;
    messages.push(message);
  };

  if (form.new_password.length < 8) {
    add("new_password", "Temporary password must contain at least 8 characters.");
  } else if (
    !/[A-Z]/.test(form.new_password)
    || !/[a-z]/.test(form.new_password)
    || !/\d/.test(form.new_password)
    || !/[^A-Za-z0-9]/.test(form.new_password)
  ) {
    add(
      "new_password",
      "Temporary password must include uppercase and lowercase letters, a number, and a special character.",
    );
  }
  if (!form.confirm_password) {
    add("confirm_password", "Confirm the temporary password.");
  } else if (form.new_password !== form.confirm_password) {
    add("confirm_password", "Temporary password and confirmation do not match.");
  }
  return localFormError(messages, errors);
}

function validateAssignmentForm(form: AssignmentForm, employee: Employee | null) {
  // Validates the employee schedule-assignment form fields.
  const errors: FieldErrors = {};
  const messages: string[] = [];
  const add = (field: string, message: string) => {
    errors[field] = message;
    messages.push(message);
  };

  if (!employee) add("employee", "Select an employee before assigning a schedule.");
  else if (!employee.is_active) add("employee", "This employee is inactive. Activate the employee before assigning a schedule.");
  if (!form.schedule_template_id) add("schedule_template_id", "Please select a schedule template.");
  if (!form.effective_from) add("effective_from", "Effective from date is required.");
  if (!form.no_end_date && !form.effective_to) add("effective_to", "Select an end date or choose No end date.");
  if (!form.no_end_date && form.effective_to && form.effective_from && form.effective_to < form.effective_from) {
    add("effective_to", "End date must be on or after the start date.");
  }
  if (!form.working_days.length) add("working_days", "Select at least one working day.");

  return localFormError(messages, errors);
}

function isCurrentAssignment(assignment: EmployeeSchedule, onDate: string): boolean {
  return assignment.is_active
    && assignment.effective_from <= onDate
    && (!assignment.effective_to || assignment.effective_to >= onDate);
}

export function EmployeesPage() {
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [active, setActive] = useState("");
  const [form, setForm] = useState<EmployeeForm | null>(null);
  const [formErrors, setFormErrors] = useState<FieldErrors>({});
  const [formMessages, setFormMessages] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [passwordReset, setPasswordReset] = useState<PasswordResetForm | null>(null);
  const [passwordResetErrors, setPasswordResetErrors] = useState<FieldErrors>({});
  const [passwordResetMessages, setPasswordResetMessages] = useState<string[]>([]);
  const [resettingPassword, setResettingPassword] = useState(false);
  const [faceEmployee, setFaceEmployee] = useState<Employee | null>(null);
  const [faceStatus, setFaceStatus] = useState<FaceStatus | null>(null);
  const [embeddings, setEmbeddings] = useState<FaceEmbeddingMetadata[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [faceMessages, setFaceMessages] = useState<string[]>([]);
  const [faceBatchValidation, setFaceBatchValidation] = useState<FaceBatchValidationState | null>(null);
  const [faceUploading, setFaceUploading] = useState<"enroll" | "re-enroll" | null>(null);
  const [confirmDiscardFaceFiles, setConfirmDiscardFaceFiles] = useState(false);
  const [scheduleEmployee, setScheduleEmployee] = useState<Employee | null>(null);
  const [scheduleDetailsEmployee, setScheduleDetailsEmployee] = useState<Employee | null>(null);
  const [employeeSchedules, setEmployeeSchedules] = useState<EmployeeSchedule[]>([]);
  const [scheduleDetailsLoading, setScheduleDetailsLoading] = useState(false);
  const [scheduleDetailsError, setScheduleDetailsError] = useState("");
  const [assignment, setAssignment] = useState<AssignmentForm>(defaultAssignment);
  const [assignmentErrors, setAssignmentErrors] = useState<FieldErrors>({});
  const [assignmentMessages, setAssignmentMessages] = useState<string[]>([]);
  const [assigning, setAssigning] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [updatingEmployeeStatus, setUpdatingEmployeeStatus] = useState(false);
  const [deactivatingFace, setDeactivatingFace] = useState(false);

  const employees = useAsync(
    // Loads the employee list using the current filters and page.
    () => listEmployees({ search: search || undefined, department_id: departmentId || undefined, is_active: active || undefined, page, page_size: 10 }),
    [search, departmentId, active, page],
  );
  const departments = useAsync(() => listDepartments({ page: 1, page_size: 100 }), []);
  const scheduleTemplates = useAsync(() => listScheduleTemplates({ page: 1, page_size: 100 }), []);

  function openCreateEmployee() {
    setFormErrors({});
    setFormMessages([]);
    setForm(emptyForm);
  }

  function editEmployee(employee: Employee) {
    setFormErrors({});
    setFormMessages([]);
    setForm({
      id: employee.id,
      email: employee.email,
      password: "",
      full_name: employee.full_name,
      employee_number: employee.employee_number,
      phone: employee.phone ?? "",
      position: employee.position ?? "",
      department_id: String(employee.department_id),
    });
  }

  function updateFormField<K extends keyof EmployeeForm>(field: K, value: EmployeeForm[K]) {
    if (!form) return;
    setForm({ ...form, [field]: value });
    setFormErrors((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  async function saveEmployee() {
    if (!form) return;
    // Runs local employee-form validation before saving.
    const localErrors = validateEmployeeForm(form);
    if (localErrors.messages.length) {
      setFormErrors(localErrors.fieldErrors);
      setFormMessages(localErrors.messages);
      return;
    }

    setSaving(true);
    setFormErrors({});
    setFormMessages([]);
    try {
      const payload = {
        email: form.email.trim().toLowerCase(),
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        position: form.position.trim() || null,
        department_id: Number(form.department_id),
      };
      if (form.id) {
        await updateEmployee(form.id, payload);
      } else {
        await createEmployee({
          ...payload,
          password: form.password,
          employee_number: form.employee_number.trim(),
        });
      }
      notify("Employee saved successfully.", "success");
      setForm(null);
      employees.refresh();
    } catch (err) {
      const parsed = parseApiError(err);
      setFormErrors(parsed.fieldErrors);
      setFormMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setSaving(false);
    }
  }

  function openPasswordReset(employee: Employee) {
    setPasswordReset({
      employee,
      new_password: "",
      confirm_password: "",
      require_password_change: true,
    });
    setPasswordResetErrors({});
    setPasswordResetMessages([]);
  }

  function updatePasswordReset(values: Partial<Omit<PasswordResetForm, "employee">>) {
    setPasswordReset((current) => current ? { ...current, ...values } : null);
    setPasswordResetErrors({});
    setPasswordResetMessages([]);
  }

  function submitPasswordReset() {
    if (!passwordReset) return;
    const validation = validatePasswordReset(passwordReset);
    if (validation.messages.length) {
      setPasswordResetErrors(validation.fieldErrors);
      setPasswordResetMessages(validation.messages);
      return;
    }
    setPendingAction({ type: "PASSWORD_RESET" });
  }

  async function performPasswordReset() {
    if (!passwordReset) return;
    setResettingPassword(true);
    setPasswordResetErrors({});
    setPasswordResetMessages([]);
    try {
      const response = await resetEmployeePassword(passwordReset.employee.id, {
        new_password: passwordReset.new_password,
        confirm_password: passwordReset.confirm_password,
        require_password_change: passwordReset.require_password_change,
      });
      notify(response.message, "success");
      setPasswordReset(null);
      setPendingAction(null);
    } catch (error) {
      const parsed = parseApiError(error);
      setPasswordResetErrors(parsed.fieldErrors);
      setPasswordResetMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setResettingPassword(false);
    }
  }

  async function performEmployeeStatusChange(employee: Employee) {
    setUpdatingEmployeeStatus(true);
    try {
      await setEmployeeActive(employee.id, !employee.is_active);
      notify("Employee status updated.", "success");
      setPendingAction(null);
      employees.refresh();
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setUpdatingEmployeeStatus(false);
    }
  }

  async function openFace(employee: Employee) {
    try {
      // Loads safe face-enrollment status and metadata for the employee.
      const [status, metadata] = await Promise.all([getFaceStatus(employee.id), listFaceEmbeddings(employee.id)]);
      setFaceEmployee(employee);
      setFaceStatus(status);
      setEmbeddings(metadata.items);
      setFiles([]);
      setFaceMessages([]);
      setFaceBatchValidation(null);
      setConfirmDiscardFaceFiles(false);
    } catch (err) {
      notify(getErrorMessage(err), "error");
    }
  }

  function appendFaceFiles(fileList: FileList | null) {
    if (!fileList?.length) return;
    setFaceBatchValidation(null);
    const selected = Array.from(fileList);
    const messages: string[] = [];
    setFiles((current) => {
      // Builds the set of already selected face-image files.
      const existing = new Set(current.map(faceFileKey));
      const additions = selected.filter((file) => {
        if (!isSupportedFaceImage(file)) {
          messages.push(`${file.name}: only JPG, JPEG, and PNG images are supported.`);
          return false;
        }
        const key = faceFileKey(file);
        if (existing.has(key)) {
          messages.push(`${file.name} has already been added.`);
          return false;
        }
        existing.add(key);
        return true;
      });
      return [...current, ...additions];
    });
    setFaceMessages(messages);
    messages.forEach((message) => notify(message, "error"));
  }

  function removeFaceFile(file: File) {
    const key = faceFileKey(file);
    setFiles((current) => current.filter((item) => faceFileKey(item) !== key));
    setFaceMessages([]);
    setFaceBatchValidation(null);
  }

  function closeFaceEnrollment({ discard = false } = {}) {
    if (faceUploading) {
      notify("Please wait for the face enrollment upload to finish.", "info");
      return;
    }
    if (!discard && files.length > 0) {
      setConfirmDiscardFaceFiles(true);
      return;
    }
    setFaceEmployee(null);
    setFaceStatus(null);
    setEmbeddings([]);
    setFiles([]);
    setFaceMessages([]);
    setFaceBatchValidation(null);
    setFaceUploading(null);
    setConfirmDiscardFaceFiles(false);
  }

  async function submitFace(mode: "enroll" | "re-enroll") {
    if (!faceEmployee || !files.length) {
      notify("Select one or more enrollment images first.", "error");
      setFaceMessages(["Please select at least one enrollment image."]);
      return;
    }
    setFaceUploading(mode);
    setFaceMessages([]);
    setFaceBatchValidation(null);
    try {
      // Uploads selected images for face enrollment or re-enrollment.
      await (mode === "enroll" ? enrollFace(faceEmployee.id, files) : reEnrollFace(faceEmployee.id, files));
      notify(mode === "enroll" ? "Face enrollment completed successfully." : "Face re-enrollment completed successfully.", "success");
      await openFace(faceEmployee);
      setFiles([]);
    } catch (err) {
      const batchValidation = parseFaceEnrollmentValidationError(err);
      if (batchValidation) {
        const invalidImageCount = new Set(
          batchValidation.errors.map((issue) => issue.position),
        ).size;
        setFaceBatchValidation({
          total: files.length,
          invalidImageCount,
          errors: batchValidation.errors,
        });
        const verb = invalidImageCount === 1 ? "needs" : "need";
        notify(`${invalidImageCount} of ${files.length} images ${verb} attention. No images were enrolled.`, "error");
        return;
      }
      const message = getErrorMessage(err) || "The selected image could not be uploaded.";
      setFaceMessages([message]);
      notify(message, "error");
    } finally {
      setFaceUploading(null);
    }
  }

  async function performFaceDeactivation() {
    if (!faceEmployee) return;
    setDeactivatingFace(true);
    try {
      await deactivateFaceEnrollment(faceEmployee.id);
      notify("Face enrollment deactivated.", "success");
      setPendingAction(null);
      await openFace(faceEmployee);
    } catch (err) {
      notify(getErrorMessage(err), "error");
    } finally {
      setDeactivatingFace(false);
    }
  }

  function openAssignSchedule(employee: Employee) {
    if (!employee.is_active) {
      notify("This employee is inactive. Activate the employee before assigning a schedule.", "error");
      return;
    }
    setScheduleEmployee(employee);
    setAssignment(defaultAssignment);
    setAssignmentErrors({});
    setAssignmentMessages([]);
  }

  async function openScheduleDetails(employee: Employee) {
    setScheduleDetailsEmployee(employee);
    setEmployeeSchedules([]);
    setScheduleDetailsError("");
    setScheduleDetailsLoading(true);
    try {
      const result = await listEmployeeSchedules(employee.id, { page: 1, page_size: 100 });
      setEmployeeSchedules(result.items);
    } catch (error) {
      setScheduleDetailsError(getErrorMessage(error));
    } finally {
      setScheduleDetailsLoading(false);
    }
  }

  function closeScheduleDetails() {
    setScheduleDetailsEmployee(null);
    setEmployeeSchedules([]);
    setScheduleDetailsError("");
  }

  function assignFromScheduleDetails() {
    if (!scheduleDetailsEmployee) return;
    const employee = scheduleDetailsEmployee;
    closeScheduleDetails();
    openAssignSchedule(employee);
  }

  function updateAssignment(values: Partial<AssignmentForm>) {
    setAssignment((current) => ({ ...current, ...values }));
    setAssignmentErrors({});
    setAssignmentMessages([]);
  }

  function submitScheduleAssignment() {
    // Submits the employee schedule-assignment form.
    const localErrors = validateAssignmentForm(assignment, scheduleEmployee);
    if (localErrors.messages.length) {
      setAssignmentErrors(localErrors.fieldErrors);
      setAssignmentMessages(localErrors.messages);
      return;
    }
    if (!scheduleEmployee) return;
    setPendingAction({ type: "SCHEDULE_ASSIGNMENT" });
  }

  async function performScheduleAssignment() {
    if (!scheduleEmployee) return;
    setAssigning(true);
    setAssignmentErrors({});
    setAssignmentMessages([]);
    try {
      await assignEmployeeSchedule(scheduleEmployee.id, {
        schedule_template_id: Number(assignment.schedule_template_id),
        effective_from: assignment.effective_from,
        effective_to: assignment.no_end_date ? null : assignment.effective_to,
        working_days: assignment.working_days,
      });
      notify("Schedule assigned. Future attendance processing will use this assignment.", "success");
      setScheduleEmployee(null);
      setPendingAction(null);
    } catch (err) {
      const parsed = parseApiError(err);
      setAssignmentErrors(parsed.fieldErrors);
      setAssignmentMessages(parsed.messages);
      notify(parsed.summary, "error");
    } finally {
      setAssigning(false);
    }
  }

  async function confirmPendingAction() {
    if (!pendingAction) return;
    if (pendingAction.type === "PASSWORD_RESET") await performPasswordReset();
    if (pendingAction.type === "EMPLOYEE_STATUS") await performEmployeeStatusChange(pendingAction.employee);
    if (pendingAction.type === "FACE_DEACTIVATION") await performFaceDeactivation();
    if (pendingAction.type === "SCHEDULE_ASSIGNMENT") await performScheduleAssignment();
  }

  function pendingActionCopy() {
    if (pendingAction?.type === "PASSWORD_RESET") {
      return {
        title: "Reset employee password?",
        description: `${passwordReset?.employee.full_name ?? "This employee"} will receive the new temporary password and existing sessions will be signed out.`,
        label: "Reset password",
        tone: "danger" as const,
      };
    }
    if (pendingAction?.type === "EMPLOYEE_STATUS") {
      const deactivate = pendingAction.employee.is_active;
      return {
        title: deactivate ? "Deactivate employee?" : "Activate employee?",
        description: deactivate
          ? `${pendingAction.employee.full_name} will no longer be able to record attendance until reactivated.`
          : `${pendingAction.employee.full_name} will regain access to active employee operations.`,
        label: deactivate ? "Deactivate" : "Activate",
        tone: deactivate ? "danger" as const : "primary" as const,
      };
    }
    if (pendingAction?.type === "FACE_DEACTIVATION") {
      return {
        title: "Deactivate face enrollment?",
        description: `${faceEmployee?.full_name ?? "This employee"} will not be recognized for attendance until a valid enrollment is active again.`,
        label: "Deactivate enrollment",
        tone: "danger" as const,
      };
    }
    return {
      title: "Assign this schedule?",
      description: "The assignment will affect future attendance processing and will not rewrite historical attendance records.",
      label: "Assign schedule",
      tone: "primary" as const,
    };
  }

  const formIsValid = form ? !validateEmployeeForm(form).messages.length : false;
  const assignmentIsValid = !validateAssignmentForm(assignment, scheduleEmployee).messages.length;

  return (
    <div className="page-stack">
      <PageHeader
        title="Employees"
        description="Manage employee profiles, account status, schedules, passwords, and face enrollment from one workspace."
        action={<Button onClick={openCreateEmployee}>Create employee</Button>}
      />
      <Card>
        <SectionHeader
          title="Find employees"
          description="Search by employee details or narrow the list by department and account status."
        />
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Search">
            <input className={inputClass} value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} placeholder="Name, email, employee number" />
          </Field>
          <Field label="Department">
            <select className={inputClass} value={departmentId} onChange={(e) => { setPage(1); setDepartmentId(e.target.value); }}>
              <option value="">All departments</option>
              {departments.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
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
        {employees.loading ? <LoadingState /> : employees.error ? <ErrorState message={employees.error} /> : (
          <>
            <DataTable
              rowKey={(row) => row.id}
              rows={employees.data?.items ?? []}
              emptyTitle="No employees match your filters"
              empty="Try changing the search term, department filter, or status filter."
              columns={[
                { header: "Employee", render: (row) => <div><p className="font-semibold">{row.full_name}</p><p className="text-xs text-slate-500">{row.email}</p></div> },
                { header: "Number", render: (row) => row.employee_number },
                { header: "Department", render: (row) => row.department_name },
                { header: "Status", render: (row) => <Badge value={row.is_active} /> },
                { header: "Actions", className: "text-right", render: (row) => <div className="flex flex-wrap justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => editEmployee(row)}>Edit</Button><Button size="sm" variant="secondary" onClick={() => openScheduleDetails(row)}>Schedules</Button><Button size="sm" variant="secondary" onClick={() => openFace(row)}>Face enrollment</Button><Button size="sm" variant="secondary" onClick={() => openPasswordReset(row)}>Reset password</Button><Button size="sm" variant={row.is_active ? "danger" : "secondary"} onClick={() => setPendingAction({ type: "EMPLOYEE_STATUS", employee: row })}>{row.is_active ? "Deactivate" : "Activate"}</Button></div> },
              ]}
            />
            <Pagination page={page} pageSize={employees.data?.page_size ?? 10} total={employees.data?.total ?? 0} onPageChange={setPage} />
          </>
        )}
      </Card>

      <Modal
        open={Boolean(scheduleDetailsEmployee)}
        title={scheduleDetailsEmployee ? `${scheduleDetailsEmployee.full_name}'s schedules` : "Employee schedules"}
        description="View the current assigned schedule and previous schedule assignments for this employee."
        onClose={closeScheduleDetails}
        size="lg"
        footer={(
          <div className="action-row">
            <Button variant="secondary" onClick={closeScheduleDetails}>Close</Button>
            <Button
              onClick={assignFromScheduleDetails}
              disabled={!scheduleDetailsEmployee?.is_active}
              title={!scheduleDetailsEmployee?.is_active ? "Activate the employee before assigning a schedule." : undefined}
            >
              Assign schedule
            </Button>
          </div>
        )}
      >
        {scheduleDetailsEmployee ? (
          <div className="space-y-5">
            <div className="grid gap-3 rounded-md border border-ocean-100 bg-ocean-50 p-4 sm:grid-cols-3">
              <Info label="Employee" value={scheduleDetailsEmployee.full_name} />
              <Info label="Employee number" value={scheduleDetailsEmployee.employee_number} />
              <Info label="Department" value={scheduleDetailsEmployee.department_name} />
            </div>

            {scheduleDetailsLoading ? (
              <LoadingState label="Loading employee schedules..." />
            ) : scheduleDetailsError ? (
              <ErrorState message={scheduleDetailsError} />
            ) : employeeSchedules.length === 0 ? (
              <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
                <p className="font-semibold text-ink">No schedule has been assigned to this employee.</p>
                <p className="mt-2 text-sm text-slate-500">Use Assign schedule to create the first effective assignment.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {employeeSchedules.map((item) => {
                  const current = isCurrentAssignment(item, todayIsoDate());
                  const template = scheduleTemplates.data?.items.find((candidate) => candidate.id === item.schedule_template_id);
                  return (
                    <article
                      key={item.id}
                      className={`rounded-md border p-4 ${current ? "border-ocean-300 bg-ocean-50" : "border-slate-200 bg-white"}`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Schedule template</p>
                          <h3 className="mt-1 text-lg font-bold text-ink">{item.schedule_template_name ?? `Template #${item.schedule_template_id}`}</h3>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {current ? <Badge value="CURRENT" label="Current assignment" /> : null}
                          <Badge value={item.is_active} label={item.is_active ? "Active" : "Inactive"} />
                        </div>
                      </div>
                      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                        <Info
                          label="Effective period"
                          value={`${formatDate(item.effective_from)} to ${item.effective_to ? formatDate(item.effective_to) : "Ongoing"}`}
                        />
                        <Info label="Working days" value={formatWorkingDays(item.working_days)} />
                        {template ? (
                          <Info
                            label="Shift time"
                            value={`${formatTime(template.start_time)} to ${formatTime(template.end_time)}${template.is_overnight ? " next day" : ""}`}
                          />
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      <Modal open={Boolean(form)} title={form?.id ? "Edit employee" : "Create employee"} description="Enter the employee's official account and workforce details." onClose={() => setForm(null)} footer={<div className="action-row"><Button variant="secondary" onClick={() => setForm(null)} disabled={saving}>Cancel</Button><Button onClick={saveEmployee} disabled={!formIsValid} loading={saving} loadingLabel="Saving...">Save employee</Button></div>}>
        {form ? (
          <div className="space-y-4">
            <FormErrorSummary messages={formMessages} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email address" required error={formErrors.email}><input className={inputClass} type="email" value={form.email} onChange={(e) => updateFormField("email", e.target.value)} autoComplete="email" /></Field>
              {!form.id ? <Field label="Password" required error={formErrors.password} hint="Use at least 6 characters."><input className={inputClass} type="password" value={form.password} onChange={(e) => updateFormField("password", e.target.value)} autoComplete="new-password" /></Field> : null}
              <Field label="Full name" required error={formErrors.full_name}><input className={inputClass} value={form.full_name} onChange={(e) => updateFormField("full_name", e.target.value)} /></Field>
              <Field
                label="Employee number"
                required
                error={formErrors.employee_number}
                hint={form.id ? "Employee number cannot be changed after creation." : undefined}
              >
                <input
                  className={`${inputClass} disabled:cursor-not-allowed disabled:bg-slate-100`}
                  value={form.employee_number}
                  onChange={(e) => updateFormField("employee_number", e.target.value)}
                  placeholder="EMP001"
                  disabled={Boolean(form.id)}
                />
              </Field>
              <Field label="Department" required error={formErrors.department_id}>
                <select className={inputClass} value={form.department_id} onChange={(e) => updateFormField("department_id", e.target.value)}>
                  <option value="">Choose department</option>
                  {departments.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </Field>
              <Field label="Phone number" error={formErrors.phone}><input className={inputClass} value={form.phone} onChange={(e) => updateFormField("phone", e.target.value)} /></Field>
              <Field label="Position" error={formErrors.position} hint="Optional. If entered, use at least 2 characters."><input className={inputClass} value={form.position} onChange={(e) => updateFormField("position", e.target.value)} /></Field>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(passwordReset)}
        title={passwordReset ? `Reset password - ${passwordReset.employee.full_name}` : "Reset password"}
        description="Set a temporary password without exposing the employee's current password."
        onClose={() => setPasswordReset(null)}
        footer={(
          <div className="action-row">
            <Button variant="secondary" onClick={() => setPasswordReset(null)} disabled={resettingPassword}>Cancel</Button>
            <Button onClick={submitPasswordReset} disabled={resettingPassword}>Reset password</Button>
          </div>
        )}
      >
        {passwordReset ? (
          <div className="space-y-4">
            <div className="rounded-md bg-amber-50 p-4 text-sm text-amber-800">
              This action replaces the employee password and signs out previously issued sessions. The current password is never displayed.
            </div>
            <FormErrorSummary messages={passwordResetMessages} />
            <Field
              label="New temporary password"
              required
              error={passwordResetErrors.new_password}
              hint="At least 8 characters with uppercase, lowercase, number, and special character."
            >
              <input
                className={inputClass}
                type="password"
                autoComplete="new-password"
                value={passwordReset.new_password}
                onChange={(event) => updatePasswordReset({ new_password: event.target.value })}
              />
            </Field>
            <Field label="Confirm temporary password" required error={passwordResetErrors.confirm_password}>
              <input
                className={inputClass}
                type="password"
                autoComplete="new-password"
                value={passwordReset.confirm_password}
                onChange={(event) => updatePasswordReset({ confirm_password: event.target.value })}
              />
            </Field>
            <label className="flex items-start gap-3 rounded-md border border-slate-200 p-4 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={passwordReset.require_password_change}
                onChange={(event) => updatePasswordReset({ require_password_change: event.target.checked })}
              />
              <span>
                <span className="block font-semibold text-ink">Require password change at next login</span>
                <span className="mt-1 block text-slate-500">The employee can only reach the secure password-change screen until a private password is created.</span>
              </span>
            </label>
          </div>
        ) : null}
      </Modal>

      <Modal open={Boolean(faceEmployee)} title={`Face enrollment${faceEmployee ? ` - ${faceEmployee.full_name}` : ""}`} description="Enrollment administration is separate from attendance capture and exposes no biometric vectors." onClose={() => closeFaceEnrollment()} footer={<div className="action-row"><Button variant="secondary" onClick={() => closeFaceEnrollment()} disabled={Boolean(faceUploading)}>Close</Button></div>}>
        {faceEmployee ? (
          <div className="space-y-5">
            <div className="rounded-md bg-ocean-50 p-4 text-sm text-ocean-700">
              Enrollment images are used only for employee face enrollment or re-enrollment. This is not an attendance capture screen.
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Info label="Has enrollment" value={faceStatus?.has_face_enrollment ? "Yes" : "No"} />
              <Info label="Active embeddings" value={faceStatus?.active_embeddings ?? 0} />
              <Info label="Model" value={faceStatus?.active_model_name ?? "Not enrolled"} />
            </div>
            <Field label="Enrollment images">
              <input
                className={inputClass}
                type="file"
                multiple
                accept="image/png,image/jpeg"
                disabled={Boolean(faceUploading)}
                onChange={(e) => {
                  appendFaceFiles(e.target.files);
                  e.currentTarget.value = "";
                }}
              />
            </Field>
            <FormErrorSummary messages={faceMessages} />
            {files.length ? (
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-ink">Selected enrollment images ({files.length})</p>
                  <p className="text-xs text-slate-500">Submitted together as one atomic batch</p>
                </div>
                {faceBatchValidation ? (
                  <div className="mt-3">
                    <Alert
                      tone="danger"
                      title={`${faceBatchValidation.invalidImageCount} of ${faceBatchValidation.total} images ${faceBatchValidation.invalidImageCount === 1 ? "needs" : "need"} attention.`}
                    >
                      <p className="font-semibold">No images were enrolled.</p>
                      <p className="mt-1">
                        Fix the highlighted {faceBatchValidation.invalidImageCount === 1 ? "image" : "images"} and submit the complete set again.
                      </p>
                    </Alert>
                  </div>
                ) : null}
                <ul className="mt-3 space-y-2">
                  {files.map((file, index) => {
                    const fileIssues = faceBatchValidation?.errors.filter(
                      (issue) => issue.position === index + 1,
                    ) ?? [];
                    const hasIssue = fileIssues.length > 0;
                    return (
                      <li
                        key={faceFileKey(file)}
                        className={`flex items-start justify-between gap-3 rounded-md border px-3 py-2.5 ${hasIssue ? "border-rose-300 bg-rose-50" : "border-slate-200 bg-slate-50"}`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-700">{file.name}</p>
                          <p className="text-xs text-slate-500">{formatFileSize(file.size)}</p>
                          {fileIssues.map((issue) => (
                            <p key={`${issue.code}:${issue.message}`} className="mt-2 text-xs font-semibold leading-relaxed text-rose-700" role="alert">
                              {issue.message}
                            </p>
                          ))}
                          {!hasIssue && faceBatchValidation ? (
                            <p className="mt-2 text-xs leading-relaxed text-slate-600">
                              No validation issue reported. This image has not been enrolled.
                            </p>
                          ) : null}
                          {!faceBatchValidation ? (
                            <p className="mt-2 text-xs text-slate-500">Ready for batch validation.</p>
                          ) : null}
                        </div>
                        <Button variant="secondary" onClick={() => removeFaceFile(file)} disabled={Boolean(faceUploading)} aria-label={`Remove ${file.name}`}>Remove</Button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : (
              <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
                Select one or more clear face images. You can choose files more than once; selected images will be collected here before upload.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => submitFace("enroll")} disabled={!files.length || Boolean(faceUploading)} loading={faceUploading === "enroll"} loadingLabel="Uploading...">Enroll face using selected images</Button>
              <Button variant="secondary" onClick={() => submitFace("re-enroll")} disabled={!files.length || Boolean(faceUploading)} loading={faceUploading === "re-enroll"} loadingLabel="Uploading...">Re-enroll face using selected images</Button>
              <Button variant="danger" onClick={() => setPendingAction({ type: "FACE_DEACTIVATION" })} disabled={Boolean(faceUploading)}>Deactivate enrollment</Button>
            </div>
            <DataTable
              rowKey={(row) => row.id}
              rows={embeddings}
              emptyTitle="No face enrollment metadata found."
              empty="Upload enrollment images above to enroll this employee."
              columns={[
                { header: "ID", render: (row) => row.id },
                { header: "Model", render: (row) => row.model_name ?? "Unknown" },
                { header: "Active", render: (row) => <Badge value={row.is_active} /> },
                { header: "Created", render: (row) => formatDateTime(row.created_at) },
              ]}
            />
          </div>
        ) : null}
      </Modal>

      <Modal
        open={confirmDiscardFaceFiles}
        title="Discard selected enrollment images?"
        onClose={() => setConfirmDiscardFaceFiles(false)}
        footer={(
          <div className="action-row">
            <Button variant="secondary" onClick={() => setConfirmDiscardFaceFiles(false)}>Keep editing</Button>
            <Button variant="danger" onClick={() => closeFaceEnrollment({ discard: true })}>Discard images</Button>
          </div>
        )}
      >
        <p className="text-sm text-slate-600">
          You have selected enrollment images that have not been uploaded yet. If you discard them, no files will be uploaded and the existing enrollment metadata will remain unchanged.
        </p>
      </Modal>

      <Modal open={Boolean(scheduleEmployee)} title="Assign schedule to employee" description="Apply an active schedule template to future attendance dates for this employee." onClose={() => setScheduleEmployee(null)} footer={<div className="action-row"><Button variant="secondary" onClick={() => setScheduleEmployee(null)} disabled={assigning}>Cancel</Button><Button onClick={submitScheduleAssignment} disabled={!assignmentIsValid || assigning}>Assign schedule</Button></div>}>
        {scheduleEmployee ? (
          <div className="space-y-5">
            <FormErrorSummary messages={assignmentMessages} />
            <div className="rounded-md bg-ocean-50 p-4 text-sm text-ocean-800">
              <p className="text-xs font-bold uppercase tracking-wide text-ocean-600">Employee</p>
              <p className="mt-1 text-base font-bold text-ink">{scheduleEmployee.full_name}</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <Info label="Employee number" value={scheduleEmployee.employee_number} />
                <Info label="Department" value={scheduleEmployee.department_name} />
                <Info label="Status" value={<Badge value={scheduleEmployee.is_active} />} />
              </div>
            </div>

            {scheduleTemplates.loading ? (
              <LoadingState />
            ) : scheduleTemplates.error ? (
              <ErrorState message={scheduleTemplates.error} />
            ) : (
              <div className="space-y-4">
                <Field label="Schedule template" required error={assignmentErrors.schedule_template_id}>
                  <select className={inputClass} value={assignment.schedule_template_id} onChange={(e) => updateAssignment({ schedule_template_id: e.target.value })}>
                    <option value="">Choose template</option>
                    {scheduleTemplates.data?.items.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Effective from" required error={assignmentErrors.effective_from} hint={formatIsoDatePreview(assignment.effective_from)}>
                    <input className={inputClass} type="date" value={assignment.effective_from} onChange={(e) => updateAssignment({ effective_from: e.target.value })} />
                  </Field>
                  <div className="space-y-3">
                    <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <input type="checkbox" checked={assignment.no_end_date} onChange={(e) => updateAssignment({ no_end_date: e.target.checked, effective_to: e.target.checked ? "" : assignment.effective_to })} />
                      No end date
                    </label>
                    {!assignment.no_end_date ? (
                      <Field label="End date" required error={assignmentErrors.effective_to} hint={formatIsoDatePreview(assignment.effective_to)}>
                        <input className={inputClass} type="date" value={assignment.effective_to} onChange={(e) => updateAssignment({ effective_to: e.target.value })} />
                      </Field>
                    ) : (
                      <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">This assignment is ongoing until an administrator changes it.</p>
                    )}
                  </div>
                </div>
                <Field label="Working days" required error={assignmentErrors.working_days} hint="Select the days this schedule applies to.">
                  <div className="flex flex-wrap gap-2">
                    {libyaWeekdayOptions.map((day) => {
                      // Renders one selectable working-day chip.
                      const selected = assignment.working_days.includes(day.value);
                      return (
                        <button
                          key={day.value}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => updateAssignment({ working_days: selected ? assignment.working_days.filter((item) => item !== day.value) : [...assignment.working_days, day.value].sort((a, b) => a - b) })}
                          className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${selected ? "border-ocean-600 bg-ocean-600 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-ocean-300"}`}
                        >
                          {day.label}
                        </button>
                      );
                    })}
                  </div>
                </Field>
                <p className="text-xs text-slate-500">Schedule assignments affect future attendance processing and do not rewrite historical attendance facts.</p>
              </div>
            )}
          </div>
        ) : null}
      </Modal>
      <ConfirmationDialog
        open={Boolean(pendingAction)}
        title={pendingActionCopy().title}
        description={pendingActionCopy().description}
        confirmLabel={pendingActionCopy().label}
        tone={pendingActionCopy().tone}
        loading={resettingPassword || updatingEmployeeStatus || deactivatingFace || assigning}
        onClose={() => {
          if (resettingPassword || updatingEmployeeStatus || deactivatingFace || assigning) return;
          setPendingAction(null);
        }}
        onConfirm={confirmPendingAction}
      />
    </div>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="border-l-2 border-slate-300 bg-slate-50 px-3 py-2.5"><p className="data-label">{label}</p><div className="data-value font-semibold">{value}</div></div>;
}
