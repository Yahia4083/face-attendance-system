import { apiClient } from "./client";
import type { EmployeeSchedule, Paginated, ScheduleTemplate } from "../types/api";

export type ScheduleTemplatePayload = {
  name: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
  check_in_grace_minutes: number;
  early_departure_tolerance_minutes: number;
};

export type EmployeeSchedulePayload = {
  schedule_template_id: number;
  effective_from: string;
  effective_to?: string | null;
  working_days: number[];
};

export async function listScheduleTemplates(params: Record<string, unknown>): Promise<Paginated<ScheduleTemplate>> {
  const { data } = await apiClient.get<Paginated<ScheduleTemplate>>("/schedule-templates", { params });
  return data;
}

export async function createScheduleTemplate(payload: ScheduleTemplatePayload): Promise<ScheduleTemplate> {
  const { data } = await apiClient.post<ScheduleTemplate>("/schedule-templates", payload);
  return data;
}

export async function updateScheduleTemplate(id: number, payload: ScheduleTemplatePayload): Promise<ScheduleTemplate> {
  const { data } = await apiClient.put<ScheduleTemplate>(`/schedule-templates/${id}`, payload);
  return data;
}

export async function setScheduleTemplateActive(id: number, active: boolean): Promise<ScheduleTemplate> {
  const { data } = await apiClient.patch<ScheduleTemplate>(`/schedule-templates/${id}/${active ? "activate" : "deactivate"}`);
  return data;
}

export async function listEmployeeSchedules(employeeId: number, params: Record<string, unknown>) {
  const { data } = await apiClient.get<Paginated<EmployeeSchedule> & { employee_id: number }>(
    `/employees/${employeeId}/schedules`,
    { params },
  );
  return data;
}

export async function assignEmployeeSchedule(employeeId: number, payload: EmployeeSchedulePayload): Promise<EmployeeSchedule> {
  const { data } = await apiClient.post<EmployeeSchedule>(`/employees/${employeeId}/schedules`, payload);
  return data;
}
