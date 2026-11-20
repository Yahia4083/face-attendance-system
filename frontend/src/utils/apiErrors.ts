import axios from "axios";

export type FieldErrors = Record<string, string>;

export type ParsedApiError = {
  summary: string;
  messages: string[];
  fieldErrors: FieldErrors;
};

const defaultFieldLabels: Record<string, string> = {
  // Maps backend field names to visible form labels.
  email: "Email address",
  password: "Password",
  current_password: "Current password",
  new_password: "New password",
  confirm_password: "Password confirmation",
  full_name: "Full name",
  employee_number: "Employee number",
  department_id: "Department",
  phone: "Phone number",
  position: "Position",
  schedule_template_id: "Schedule template",
  effective_from: "Effective from",
  effective_to: "End date",
  working_days: "Working days",
  name: "Name",
  description: "Description",
  start_time: "Start time",
  end_time: "End time",
  check_in_grace_minutes: "Check-in grace minutes",
  early_departure_tolerance_minutes: "Early departure tolerance",
  reason: "Reason",
  reviewer_note: "Reviewer note",
  approved_minutes: "Approved minutes",
  corrected_status: "Corrected status",
  value: "Value",
};

const fieldAliases: Record<string, string> = {
  employee_id: "employee_number",
};

function normalizeField(rawField: unknown): string | undefined {
  if (typeof rawField !== "string" && typeof rawField !== "number") return undefined;
  const value = String(rawField);
  return fieldAliases[value] ?? value;
}

function labelFor(field: string | undefined, labels: Record<string, string>): string {
  if (!field) return "This field";
  return labels[field] ?? defaultFieldLabels[field] ?? field.replaceAll("_", " ");
}

function humanizeValidationMessage(detail: any, labels: Record<string, string>): { field?: string; message: string } {
  // Converts one FastAPI validation error into a field message.
  const loc = Array.isArray(detail?.loc) ? detail.loc : [];
  const field = normalizeField(loc[loc.length - 1]);
  const label = labelFor(field, labels);
  const msg = String(detail?.msg ?? "").trim();
  const type = String(detail?.type ?? "");
  const ctx = detail?.ctx ?? {};

  if (type.includes("missing") || msg.toLowerCase() === "field required") {
    return { field, message: `${label} is required.` };
  }

  if (type.includes("string_too_short") || msg.toLowerCase().includes("at least")) {
    const min = ctx.min_length ?? 2;
    return { field, message: `${label} must be at least ${min} characters.` };
  }

  if (type.includes("string_too_long")) {
    const max = ctx.max_length ?? "the allowed number of";
    return { field, message: `${label} must be no more than ${max} characters.` };
  }

  if (type.includes("greater_than") || msg.toLowerCase().includes("greater than 0")) {
    return { field, message: `Please select a valid ${label.toLowerCase()}.` };
  }

  if (type.includes("int_parsing") || type.includes("int_type")) {
    return { field, message: `${label} must be a valid number.` };
  }

  if (type.includes("date") || msg.toLowerCase().includes("valid date")) {
    return { field, message: `${label} must be a valid date.` };
  }

  if (type.includes("time") || msg.toLowerCase().includes("valid time")) {
    return { field, message: `${label} must be a valid time.` };
  }

  if (type.includes("email") || msg.toLowerCase().includes("valid email")) {
    return { field, message: "Please enter a valid email address." };
  }

  return { field, message: field ? `${label}: ${msg || "Please check this value."}` : msg || "Please check the submitted values." };
}

function messageFromString(detail: string): { field?: string; message: string } {
  // Converts one backend business-rule message into a UI message.
  const text = detail.trim();
  const lower = text.toLowerCase();

  if (lower.includes("employee email already exists")) return { field: "email", message: "Email address is already used by another employee." };
  if (lower.includes("email address is already used")) return { field: "email", message: "This email address is already used by another account." };
  if (lower.includes("employee number already exists")) return { field: "employee_number", message: "Employee number is already used by another employee." };
  if (lower.includes("department name already exists")) return { field: "name", message: "Department name already exists. Please choose a different name." };
  if (lower.includes("schedule template name already exists")) return { field: "name", message: "Schedule template name already exists. Please choose a different name." };
  if (lower.includes("department not found")) return { field: "department_id", message: "Please select a valid department." };
  if (lower.includes("department must be active")) return { field: "department_id", message: "Please select an active department." };
  if (lower.includes("employee not found")) return { field: "employee_number", message: "No employee found with this employee number." };
  if (lower.includes("employee is inactive")) return { field: "employee_number", message: "This employee is inactive and cannot receive a schedule assignment." };
  if (lower.includes("schedule template not found")) return { field: "schedule_template_id", message: "Please select a valid schedule template." };
  if (lower.includes("schedule template is inactive")) return { field: "schedule_template_id", message: "Please select an active schedule template." };
  if (lower.includes("effective end date")) return { field: "effective_to", message: "End date must be on or after the start date." };
  if (lower.includes("at least one working day")) return { field: "working_days", message: "Select at least one working day." };
  if (lower.includes("working days must contain unique")) return { field: "working_days", message: "Each working day can be selected only once." };
  if (lower.includes("working days must be integers")) return { field: "working_days", message: "Select valid working days." };
  if (lower.includes("overlapping active schedule")) return { message: "This employee already has an active schedule assignment that overlaps the selected dates." };
  if (lower.includes("start time and end time")) return { field: "end_time", message: "Start time and end time must be different." };
  if (lower.includes("end time must be later")) return { field: "end_time", message: "End time must be later than start time for a daytime schedule." };
  if (lower.includes("overnight schedules")) return { field: "end_time", message: "For an overnight schedule, the end time must be on the next calendar date." };
  if (lower.includes("check-in grace")) return { field: "check_in_grace_minutes", message: "Check-in grace minutes must be between 0 and 120." };
  if (lower.includes("early departure")) return { field: "early_departure_tolerance_minutes", message: "Early departure tolerance must be between 0 and 120 minutes." };
  if (lower.includes("update reason")) return { field: "reason", message: "Reason must be between 5 and 500 characters." };
  if (lower.includes("correction reason")) return { field: "reason", message: "Correction reason must be between 10 and 1000 characters." };
  if (lower.includes("justification request has already been submitted")) return { message: "A justification request has already been submitted for this attendance record." };
  if (lower.includes("monthly justification limit")) return { message: "You have reached the monthly justification limit." };
  if (lower.includes("invalid justification request type")) return { field: "request_type", message: "Please select a valid justification type." };
  if (lower.includes("not eligible for this justification")) return { field: "attendance_record_id", message: "This attendance record is not eligible for the selected justification type." };
  if (lower.includes("must be between") && lower.includes("organization_name")) return { field: "value", message: "Organization name must be between 2 and 150 characters." };
  if (lower.includes("must be between") && lower.includes("attendance_processing_delay_minutes")) return { field: "value", message: "Attendance processing delay must be between 0 and 1440 minutes." };
  if (lower.includes("must be between") && lower.includes("attendance_early_check_in_window_minutes")) return { field: "value", message: "Early check-in window must be between 0 and 720 minutes." };
  if (lower.includes("must be between") && lower.includes("overtime_minimum_minutes")) return { field: "value", message: "Overtime minimum must be between 1 and 720 minutes." };
  if (lower.includes("must be between") && lower.includes("justification_monthly_limit")) return { field: "value", message: "Monthly justification limit must be between 0 and 31." };
  if (lower.includes("current password is incorrect")) return { field: "current_password", message: "Current password is incorrect." };
  if (lower.includes("confirmation do not match")) return { field: "confirm_password", message: "New password and confirmation do not match." };
  if (lower.includes("different from the current password")) return { field: "new_password", message: "New password must be different from the current password." };
  if (lower.includes("password must contain at least")) return { field: "new_password", message: "New password must contain at least 8 characters." };
  if (lower.includes("password must include")) return { field: "new_password", message: "New password must include uppercase and lowercase letters, a number, and a special character." };

  if (lower.includes("forbidden") || lower.includes("permission")) {
    return { message: "You do not have permission to perform this action." };
  }

  return { message: text || "Something went wrong. Please try again." };
}

export function parseApiError(error: unknown, fieldLabels: Record<string, string> = {}): ParsedApiError {
  // Converts an API error into summary, list, and field errors.
  const labels = { ...defaultFieldLabels, ...fieldLabels };
  const fieldErrors: FieldErrors = {};
  const messages: string[] = [];

  function addError(entry: { field?: string; message: string }) {
    if (entry.field && !fieldErrors[entry.field]) fieldErrors[entry.field] = entry.message;
    messages.push(entry.message);
  }

  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (Array.isArray(detail)) {
      detail.forEach((item) => addError(humanizeValidationMessage(item, labels)));
    } else if (typeof detail === "string") {
      addError(messageFromString(detail));
    } else if (detail) {
      addError({ message: "Please check the form values and try again." });
    } else if (error.response?.status === 403) {
      addError({ message: "You do not have permission to perform this action." });
    } else if (error.response?.status === 401) {
      addError({ message: "Your session has expired. Please sign in again." });
    } else {
      addError({ message: "The request could not be completed. Please try again." });
    }
  } else if (error instanceof Error) {
    addError(messageFromString(error.message));
  } else {
    addError({ message: "Something went wrong. Please try again." });
  }

  const uniqueMessages = Array.from(new Set(messages.filter(Boolean)));
  return {
    summary: uniqueMessages[0] ?? "Something went wrong. Please try again.",
    messages: uniqueMessages,
    fieldErrors,
  };
}

export function localFormError(messages: string[], fieldErrors: FieldErrors = {}): ParsedApiError {
  const uniqueMessages = Array.from(new Set(messages));
  return {
    summary: uniqueMessages[0] ?? "Please check the form values.",
    messages: uniqueMessages,
    fieldErrors,
  };
}
