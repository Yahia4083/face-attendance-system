export function formatEnumLabel(value?: string | null, fallback = "Not set"): string {
  if (!value) return fallback;
  return value
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatMinutes(value?: number | null): string {
  return value == null ? "Not available" : `${value} min`;
}

export function formatHours(value?: number | null): string {
  return value == null ? "Not available" : `${Number(value).toFixed(2)} hours`;
}
