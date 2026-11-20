export const BUSINESS_TIMEZONE = "Africa/Tripoli";

export function formatDate(value?: string | null): string {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatIsoDatePreview(value?: string | null): string {
  if (!value) return "No date selected";
  return `Selected: ${formatDate(value)} (${value})`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: BUSINESS_TIMEZONE,
  }).format(date);
}

export function formatTime(value?: string | null): string {
  if (!value) return "Not set";
  const match = value.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return value;
  const hours = Number(match[1]);
  const minutes = match[2];
  if (hours < 0 || hours > 23) return value;
  const suffix = hours >= 12 ? "PM" : "AM";
  const displayHours = hours % 12 || 12;
  return `${String(displayHours).padStart(2, "0")}:${minutes} ${suffix}`;
}

export function todayIsoDate(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BUSINESS_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function toInputMonth(value = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BUSINESS_TIMEZONE,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(value);
  const resolved = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${resolved.year}-${resolved.month}`;
}

// Backend uses Python/ISO weekday values: 0=Monday ... 6=Sunday.
export const weekdayLabels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const libyaWeekdayOptions = [
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
];

const weekdayDisplayOrder = new Map(libyaWeekdayOptions.map((item, index) => [item.value, index]));

export function formatWorkingDays(days: number[]): string {
  if (!days.length) return "No days selected";
  return [...days]
    .sort((a, b) => (weekdayDisplayOrder.get(a) ?? 99) - (weekdayDisplayOrder.get(b) ?? 99))
    .map((day) => weekdayLabels[day] ?? `Day ${day}`)
    .join(", ");
}
