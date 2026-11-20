import { apiClient } from "./client";
import type { Department, Paginated } from "../types/api";

export type DepartmentPayload = {
  name: string;
  description?: string | null;
};

export async function listDepartments(params: Record<string, unknown> = {}): Promise<Paginated<Department>> {
  const { data } = await apiClient.get<Paginated<Department>>("/departments", { params });
  return data;
}

export async function createDepartment(payload: DepartmentPayload): Promise<Department> {
  const { data } = await apiClient.post<Department>("/departments", payload);
  return data;
}

export async function updateDepartment(id: number, payload: DepartmentPayload): Promise<Department> {
  const { data } = await apiClient.put<Department>(`/departments/${id}`, payload);
  return data;
}

export async function setDepartmentActive(id: number, active: boolean): Promise<Department> {
  const { data } = await apiClient.patch<Department>(`/departments/${id}/${active ? "activate" : "deactivate"}`);
  return data;
}
