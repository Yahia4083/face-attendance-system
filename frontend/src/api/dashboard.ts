import { apiClient } from "./client";
import type {
  DashboardActivity,
  DashboardSummary,
  DashboardTable,
  DashboardTrendItem,
  DepartmentDashboardItem,
  Paginated,
  PendingRequests,
} from "../types/api";

export async function getDashboardSummary(onDate?: string): Promise<DashboardSummary> {
  const { data } = await apiClient.get<DashboardSummary>("/dashboard/summary", {
    params: { on_date: onDate || undefined },
  });
  return data;
}

export async function getDashboardAttendance(params: Record<string, unknown>): Promise<DashboardTable> {
  const { data } = await apiClient.get<DashboardTable>("/dashboard/today-attendance", { params });
  return data;
}

export async function getPendingRequests(params: Record<string, unknown>): Promise<PendingRequests> {
  const { data } = await apiClient.get<PendingRequests>("/dashboard/pending-requests", { params });
  return data;
}

export async function getDepartmentDashboard(params: Record<string, unknown>) {
  const { data } = await apiClient.get<Paginated<DepartmentDashboardItem> & { on_date: string; timezone: string }>(
    "/dashboard/department-summary",
    { params },
  );
  return data;
}

export async function getAttendanceTrend(params: Record<string, unknown>) {
  const { data } = await apiClient.get<{
    trend_type: string;
    date_from: string;
    date_to: string;
    days: number;
    timezone: string;
    items: DashboardTrendItem[];
  }>("/dashboard/attendance-trend", { params });
  return data;
}

export async function getRecentActivity(limit = 10): Promise<{ items: DashboardActivity[] }> {
  const { data } = await apiClient.get<{ items: DashboardActivity[] }>("/dashboard/recent-activity", {
    params: { limit },
  });
  return data;
}
