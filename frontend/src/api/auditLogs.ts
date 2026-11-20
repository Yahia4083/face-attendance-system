import type { AuditLogListResponse } from "../types/audit";
import { apiClient } from "./client";

export type AuditLogQuery = {
  date_from?: string;
  date_to?: string;
  action?: string;
  actor?: string;
  entity_type?: string;
  page: number;
  page_size: number;
};

export async function listAuditLogs(params: AuditLogQuery): Promise<AuditLogListResponse> {
  const { data } = await apiClient.get<AuditLogListResponse>("/audit-logs", { params });
  return data;
}
