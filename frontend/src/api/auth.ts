import { apiClient } from "./client";
import type { CurrentUser, LoginResponse } from "../types/api";

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/login", { email, password });
  return data;
}

export async function getMe(): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>("/auth/me");
  return data;
}

export async function changeOwnPassword(payload: {
  current_password: string;
  new_password: string;
  confirm_password: string;
}): Promise<{ message: string; must_change_password: boolean }> {
  const { data } = await apiClient.patch<{
    message: string;
    must_change_password: boolean;
  }>("/auth/me/password", payload);
  return data;
}
