import { BUSINESS_TIMEZONE } from "./dateTime";
import { formatEnumLabel } from "./formatters";

const actionLabels: Record<string, string> = {
  ACTIVATE_DEPARTMENT: "Department Activated",
  ACTIVATE_EMPLOYEE: "Employee Activated",
  ACTIVATE_SCHEDULE_TEMPLATE: "Schedule Template Activated",
  ADMIN_RESET_EMPLOYEE_PASSWORD: "Employee Password Reset",
  APPROVE_JUSTIFICATION_REQUEST: "Justification Approved",
  APPROVE_OVERTIME_REQUEST: "Overtime Approved",
  ASSIGN_EMPLOYEE_SCHEDULE: "Schedule Assigned",
  ATTENDANCE_CHECK_IN: "Attendance Check-In",
  ATTENDANCE_CHECK_OUT: "Attendance Check-Out",
  CREATE_ABSENT_ATTENDANCE: "Absence Record Created",
  CREATE_ATTENDANCE_CORRECTION: "Attendance Correction Created",
  CREATE_DEPARTMENT: "Department Created",
  CREATE_EMPLOYEE: "Employee Created",
  CREATE_JUSTIFICATION_REQUEST: "Justification Submitted",
  CREATE_OVERTIME_REQUEST: "Overtime Request Submitted",
  CREATE_SCHEDULE_TEMPLATE: "Schedule Template Created",
  CHANGE_OWN_PASSWORD: "Password Changed",
  DEACTIVATE_DEPARTMENT: "Department Deactivated",
  DEACTIVATE_EMPLOYEE: "Employee Deactivated",
  DEACTIVATE_EMPLOYEE_SCHEDULE: "Schedule Assignment Deactivated",
  DEACTIVATE_FACE_ENROLLMENT: "Face Enrollment Deactivated",
  DEACTIVATE_SCHEDULE_TEMPLATE: "Schedule Template Deactivated",
  ENROLL_FACE: "Face Enrollment Created",
  EXPORT_ATTENDANCE_REPORT: "Attendance Report Exported",
  EXPORT_OWN_ATTENDANCE_REPORT: "Personal Attendance Report Exported",
  LIVE_ATTENDANCE_REJECTED: "Live Attendance Rejected",
  LIVENESS_VERIFICATION_FAILED: "Live Verification Failed",
  LOGIN_FAILED: "Sign-In Failed",
  LOGIN_SUCCESS: "Signed In",
  PROCESS_DAILY_ATTENDANCE: "Daily Attendance Processed",
  MARK_MISSING_CHECKOUT: "Missing Checkout Recorded",
  RE_ENROLL_FACE: "Face Enrollment Updated",
  REJECT_JUSTIFICATION_REQUEST: "Justification Rejected",
  REJECT_OVERTIME_REQUEST: "Overtime Rejected",
  UPDATE_DEPARTMENT: "Department Updated",
  UPDATE_EMPLOYEE: "Employee Updated",
  UPDATE_EMPLOYEE_SCHEDULE: "Schedule Assignment Updated",
  ACTIVATE_EMPLOYEE_SCHEDULE: "Schedule Assignment Activated",
  UPDATE_SCHEDULE_TEMPLATE: "Schedule Template Updated",
  UPDATE_SYSTEM_SETTING: "System Setting Updated",
};

export type AuditActionCategory =
  | "EMPLOYEE"
  | "SCHEDULE"
  | "ATTENDANCE"
  | "REQUEST"
  | "SETTINGS"
  | "AUTHENTICATION"
  | "SYSTEM";

export function formatAuditAction(action: string): string {
  return actionLabels[action] ?? formatEnumLabel(action, "System Activity");
}

export function auditActionCategory(action: string): AuditActionCategory {
  if (action.includes("LOGIN") || action.includes("PASSWORD")) return "AUTHENTICATION";
  if (action.includes("SETTING")) return "SETTINGS";
  if (action.includes("JUSTIFICATION") || action.includes("OVERTIME")) return "REQUEST";
  if (action.includes("SCHEDULE")) return "SCHEDULE";
  if (action.includes("EMPLOYEE") || action.includes("FACE_ENROLLMENT") || action.includes("ENROLL_FACE")) return "EMPLOYEE";
  if (action.includes("ATTENDANCE") || action.includes("CHECK_IN") || action.includes("CHECK_OUT") || action.includes("CHECKOUT") || action.includes("LIVENESS")) return "ATTENDANCE";
  return "SYSTEM";
}

export function auditCategoryLabel(category: AuditActionCategory): string {
  return formatEnumLabel(category);
}

export function auditCategoryClass(category: AuditActionCategory): string {
  const classes: Record<AuditActionCategory, string> = {
    EMPLOYEE: "bg-sky-50 text-sky-700 ring-sky-200",
    SCHEDULE: "bg-indigo-50 text-indigo-700 ring-indigo-200",
    ATTENDANCE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    REQUEST: "bg-amber-50 text-amber-700 ring-amber-200",
    SETTINGS: "bg-slate-100 text-slate-700 ring-slate-200",
    AUTHENTICATION: "bg-rose-50 text-rose-700 ring-rose-200",
    SYSTEM: "bg-slate-100 text-slate-700 ring-slate-200",
  };
  return classes[category];
}

export function formatAuditDateTime(value: string): { date: string; time: string } {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return { date: value, time: "" };
  return {
    date: new Intl.DateTimeFormat("en", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      timeZone: BUSINESS_TIMEZONE,
    }).format(parsed),
    time: new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
      timeZone: BUSINESS_TIMEZONE,
    }).format(parsed),
  };
}

export function formatAuditMetadataKey(key: string): string {
  const withSpaces = key.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  return formatEnumLabel(withSpaces);
}
