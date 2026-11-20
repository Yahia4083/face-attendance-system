import { apiClient } from "./client";
import type { SystemSetting } from "../types/api";

export async function listSystemSettings(params: Record<string, unknown> = {}): Promise<{ items: SystemSetting[] }> {
  const { data } = await apiClient.get<{ items: SystemSetting[] }>("/system-settings", { params });
  return data;
}

export async function getSystemSetting(key: string): Promise<SystemSetting> {
  const { data } = await apiClient.get<SystemSetting>(`/system-settings/${key}`);
  return data;
}

export async function updateSystemSetting(key: string, payload: { value: unknown; reason?: string }) {
  const { data } = await apiClient.put(`/system-settings/${key}`, payload);
  return data;
}
