import { apiClient } from "./client";
import type { Paginated, ReportSummary } from "../types/api";

export type ReportRow = {
  attendance_id: number;
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  department_name?: string | null;
  schedule_date: string;
  schedule_template_name?: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  status: string;
  latest_justification_status?: string | null;
  latest_overtime_status?: string | null;
};

export type MonthlyReportRow = {
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  scheduled_processed_shift_count: number;
  scheduled_attended_shift_count: number;
  absent_count: number;
  late_count: number;
  early_departure_count: number;
  missing_checkout_count: number;
  unscheduled_attendance_count: number;
  approved_justification_count?: number;
  approved_overtime_minutes: number;
  attendance_rate_percentage: number | null;
};

export async function getDailyReport(params: Record<string, unknown>) {
  const { data } = await apiClient.get<
    Paginated<ReportRow> & {
      report_type: string;
      on_date: string;
      timezone: string;
      summary: ReportSummary;
      data_basis: string;
      requires_daily_processing_for_complete_absence_metrics: boolean;
    }
  >("/reports/attendance/daily", { params });
  return data;
}

export async function getMonthlyReport(params: Record<string, unknown>) {
  const { data } = await apiClient.get<
    Paginated<MonthlyReportRow> & {
      report_type: string;
      year: number;
      month: number;
      date_from: string;
      date_to: string;
      timezone: string;
      summary: ReportSummary;
      data_basis: string;
      requires_daily_processing_for_complete_absence_metrics: boolean;
    }
  >("/reports/attendance/monthly", { params });
  return data;
}

export async function getEmployeeSummary(employeeId: number, params: Record<string, unknown>) {
  const { data } = await apiClient.get(`/reports/employees/${employeeId}/summary`, { params });
  return data;
}

export async function getDepartmentSummary(departmentId: number, params: Record<string, unknown>) {
  const { data } = await apiClient.get(`/reports/departments/${departmentId}/summary`, { params });
  return data;
}

export async function exportAttendanceReport(params: Record<string, unknown>) {
  const response = await apiClient.get<Blob>("/reports/attendance/export", {
    params,
    responseType: "blob",
  });
  return response;
}
