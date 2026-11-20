import { apiClient } from "./client";
import type {
  AttendanceRecord,
  EffectiveSchedule,
  EmployeeAttendanceSummary,
  JustificationRequest,
  OvertimeRequest,
  Paginated,
} from "../types/api";

export async function listMyAttendance(params: Record<string, unknown>): Promise<Paginated<AttendanceRecord>> {
  const { data } = await apiClient.get<Paginated<AttendanceRecord>>("/me/attendance", { params });
  return data;
}

export async function getMyEffectiveSchedule(onDate: string): Promise<EffectiveSchedule> {
  const { data } = await apiClient.get<EffectiveSchedule>("/me/schedules/effective", {
    params: { on_date: onDate },
  });
  return data;
}

export async function listMyJustificationRequests(params: Record<string, unknown>): Promise<Paginated<JustificationRequest>> {
  const { data } = await apiClient.get<Paginated<JustificationRequest>>("/me/justification-requests", { params });
  return data;
}

export async function listMyOvertimeRequests(params: Record<string, unknown>): Promise<Paginated<OvertimeRequest>> {
  const { data } = await apiClient.get<Paginated<OvertimeRequest>>("/me/overtime-requests", { params });
  return data;
}

export async function createMyJustificationRequest(
  attendanceId: number,
  payload: { request_type: string; reason: string },
): Promise<JustificationRequest> {
  const { data } = await apiClient.post<JustificationRequest>(
    `/me/attendance/${attendanceId}/justification-requests`,
    payload,
  );
  return data;
}

export async function createMyOvertimeRequest(
  attendanceId: number,
  payload: { requested_minutes: number; reason: string },
): Promise<OvertimeRequest> {
  const { data } = await apiClient.post<OvertimeRequest>(`/me/attendance/${attendanceId}/overtime-requests`, payload);
  return data;
}

export async function getMyAttendanceSummary(params: { date_from: string; date_to: string }): Promise<EmployeeAttendanceSummary> {
  const { data } = await apiClient.get<EmployeeAttendanceSummary>("/me/reports/attendance-summary", { params });
  return data;
}

export async function exportMyAttendanceReport(params: { date_from: string; date_to: string; format: "csv" | "xlsx" }) {
  return apiClient.get<Blob>("/me/reports/attendance/export", {
    params,
    responseType: "blob",
  });
}
