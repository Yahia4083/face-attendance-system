import { parseApiError } from "./apiErrors";

export function getErrorMessage(error: unknown): string {
  return parseApiError(error).summary;
}
