import axios from "axios";

// Defines the backend API base URL for all frontend requests.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:55000";

export const tokenStorageKey = "attendance_admin_token";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  // Attaches the saved JWT token to protected API requests.
  const token = localStorage.getItem(tokenStorageKey);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Clears the session when the backend returns an unauthorized response.
    if (error.response?.status === 401) {
      localStorage.removeItem(tokenStorageKey);
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
    return Promise.reject(error);
  },
);

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
