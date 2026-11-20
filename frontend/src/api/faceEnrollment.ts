import axios from "axios";

import { apiClient } from "./client";

export type FaceStatus = {
  employee_id: number;
  employee_name: string;
  has_face_enrollment: boolean;
  active_embeddings: number;
  inactive_embeddings: number;
  latest_enrollment_at?: string | null;
  active_model_name?: string | null;
};

export type FaceEmbeddingMetadata = {
  id: number;
  image_path: string;
  model_name?: string | null;
  is_active: boolean;
  created_at: string;
};

export type FaceImageValidationIssue = {
  filename: string;
  code: string;
  message: string;
  position: number;
};

export type FaceEnrollmentBatchValidation = {
  message: string;
  errors: FaceImageValidationIssue[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseFaceEnrollmentValidationError(
  error: unknown,
): FaceEnrollmentBatchValidation | null {
  if (!axios.isAxiosError(error)) return null;

  const detail = error.response?.data?.detail;
  if (!isObject(detail) || !Array.isArray(detail.errors)) return null;

  const errors = detail.errors.flatMap((item): FaceImageValidationIssue[] => {
    if (!isObject(item)) return [];
    if (
      typeof item.filename !== "string"
      || typeof item.code !== "string"
      || typeof item.message !== "string"
      || typeof item.position !== "number"
    ) {
      return [];
    }
    return [{
      filename: item.filename,
      code: item.code,
      message: item.message,
      position: item.position,
    }];
  });

  if (!errors.length) return null;
  return {
    message: typeof detail.message === "string"
      ? detail.message
      : "Some enrollment images need attention.",
    errors,
  };
}

function filesToFormData(files: FileList | File[]): FormData {
  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append("files", file));
  return formData;
}

export async function getFaceStatus(employeeId: number): Promise<FaceStatus> {
  const { data } = await apiClient.get<FaceStatus>(`/employees/${employeeId}/face/status`);
  return data;
}

export async function listFaceEmbeddings(employeeId: number): Promise<{ employee_id: number; items: FaceEmbeddingMetadata[] }> {
  const { data } = await apiClient.get<{ employee_id: number; items: FaceEmbeddingMetadata[] }>(
    `/employees/${employeeId}/face/embeddings`,
  );
  return data;
}

export async function enrollFace(employeeId: number, files: FileList | File[]) {
  const { data } = await apiClient.post(`/employees/${employeeId}/face/enroll`, filesToFormData(files), {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function reEnrollFace(employeeId: number, files: FileList | File[]) {
  const { data } = await apiClient.post(`/employees/${employeeId}/face/re-enroll`, filesToFormData(files), {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deactivateFaceEnrollment(employeeId: number) {
  const { data } = await apiClient.patch(`/employees/${employeeId}/face/deactivate`);
  return data;
}
