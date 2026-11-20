import type { AttendanceRecord } from "../types/api";

export function inferredJustificationType(record?: AttendanceRecord | null): string | null {
  if (!record) return null;
  const status = record.effective_status || record.status;
  if (record.is_late || status === "LATE") return "LATE";
  if (record.is_early_departure || status === "EARLY_DEPARTURE") return "EARLY_DEPARTURE";
  if (record.is_missing_checkout || status === "MISSING_CHECKOUT") return "MISSING_CHECKOUT";
  return null;
}

export function canRequestAttendanceReview(record?: AttendanceRecord | null): boolean {
  return Boolean(record && !record.latest_justification_status && !record.has_pending_justification && inferredJustificationType(record));
}

export function requestReviewPath(record: AttendanceRecord): string {
  const params = new URLSearchParams({
    attendanceRecordId: String(record.id),
  });
  const requestType = inferredJustificationType(record);
  if (requestType) params.set("requestType", requestType);
  return `/employee/requests?${params.toString()}`;
}
