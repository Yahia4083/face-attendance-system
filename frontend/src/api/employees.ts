import { apiClient } from "./client";
import type { Employee, Paginated } from "../types/api";

export type EmployeePayload = {
  email?: string;
  password?: string;
  full_name: string;
  employee_number?: string;
  phone?: string | null;
  position?: string | null;
  department_id: number;
};

export async function listEmployees(params: Record<string, unknown>): Promise<Paginated<Employee>> {
  const { data } = await apiClient.get<Paginated<Employee>>("/employees", { params });
  return data;
}

export async function getEmployee(id: number): Promise<Employee> {
  const { data } = await apiClient.get<Employee>(`/employees/${id}`);
  return data;
}

export async function getEmployeeByNumber(employeeNumber: string): Promise<Employee> {
  const { data } = await apiClient.get<Employee>("/employees/lookup/by-number", {
    params: { employee_number: employeeNumber },
  });
  return data;
}

export async function createEmployee(payload: Required<Pick<EmployeePayload, "email" | "password" | "full_name" | "employee_number" | "department_id">> & Partial<EmployeePayload>): Promise<Employee> {
  const { data } = await apiClient.post<Employee>("/employees", payload);
  return data;
}

export async function updateEmployee(
  id: number,
  payload: Omit<EmployeePayload, "password" | "employee_number">,
): Promise<Employee> {
  const { data } = await apiClient.put<Employee>(`/employees/${id}`, payload);
  return data;
}

export async function setEmployeeActive(id: number, active: boolean): Promise<Employee> {
  const { data } = await apiClient.patch<Employee>(`/employees/${id}/${active ? "activate" : "deactivate"}`);
  return data;
}

export async function resetEmployeePassword(
  id: number,
  payload: {
    new_password: string;
    confirm_password: string;
    require_password_change: boolean;
  },
): Promise<{
  employee_id: number;
  user_id: number;
  require_password_change: boolean;
  message: string;
}> {
  const { data } = await apiClient.patch(
    `/employees/${id}/account/password`,
    payload,
  );
  return data;
}
