import { apiClient } from "./client";
import type { JustificationRequest, OvertimeRequest, Paginated } from "../types/api";

export async function listJustificationRequests(params: Record<string, unknown>): Promise<Paginated<JustificationRequest>> {
  const { data } = await apiClient.get<Paginated<JustificationRequest>>("/justification-requests", { params });
  return data;
}

export async function approveJustification(id: number, reviewer_note?: string): Promise<JustificationRequest> {
  const { data } = await apiClient.patch<JustificationRequest>(`/justification-requests/${id}/approve`, { reviewer_note });
  return data;
}

export async function rejectJustification(id: number, reviewer_note?: string): Promise<JustificationRequest> {
  const { data } = await apiClient.patch<JustificationRequest>(`/justification-requests/${id}/reject`, { reviewer_note });
  return data;
}

export async function listOvertimeRequests(params: Record<string, unknown>): Promise<Paginated<OvertimeRequest>> {
  const { data } = await apiClient.get<Paginated<OvertimeRequest>>("/overtime-requests", { params });
  return data;
}

export async function approveOvertime(id: number, payload: { approved_minutes: number; reviewer_note?: string }): Promise<OvertimeRequest> {
  const { data } = await apiClient.patch<OvertimeRequest>(`/overtime-requests/${id}/approve`, payload);
  return data;
}

export async function rejectOvertime(id: number, reviewer_note?: string): Promise<OvertimeRequest> {
  const { data } = await apiClient.patch<OvertimeRequest>(`/overtime-requests/${id}/reject`, { reviewer_note });
  return data;
}
