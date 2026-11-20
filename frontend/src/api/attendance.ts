import { apiClient } from "./client";
import type {
  AttendanceCorrection,
  AttendanceRecord,
  Paginated,
  ProcessDailyAttendanceResult,
} from "../types/api";

export async function listAttendance(params: Record<string, unknown>): Promise<Paginated<AttendanceRecord>> {
  const { data } = await apiClient.get<Paginated<AttendanceRecord>>("/attendance/records", { params });
  return data;
}

export async function getAttendanceRecord(id: number): Promise<AttendanceRecord> {
  const { data } = await apiClient.get<AttendanceRecord>(`/attendance/records/${id}`);
  return data;
}

export async function createAttendanceCorrection(
  attendanceId: number,
  payload: { corrected_status: string; reason: string },
): Promise<AttendanceCorrection> {
  const { data } = await apiClient.post<AttendanceCorrection>(
    `/attendance/records/${attendanceId}/corrections`,
    payload,
  );
  return data;
}

export async function listAttendanceCorrections(attendanceId: number) {
  const { data } = await apiClient.get<{ items: AttendanceCorrection[]; total: number }>(
    `/attendance/records/${attendanceId}/corrections`,
  );
  return data;
}

export async function processDailyAttendance(onDate: string): Promise<ProcessDailyAttendanceResult> {
  const { data } = await apiClient.post<ProcessDailyAttendanceResult>("/attendance/process-daily", { on_date: onDate });
  return data;
}
