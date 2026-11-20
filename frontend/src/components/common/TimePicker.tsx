import { Clock3 } from "lucide-react";
import { useId } from "react";

type Period = "AM" | "PM";

type TimeParts = {
  hour: number;
  minute: number;
  period: Period;
};

const hours = Array.from({ length: 12 }, (_, index) => index + 1);
const minutes = Array.from({ length: 60 }, (_, index) => index);

function parseTime(value?: string | null): TimeParts {
  const [rawHour, rawMinute] = String(value ?? "08:00").split(":");
  const parsedHour = Number(rawHour);
  const parsedMinute = Number(rawMinute);
  const hour24 = Number.isInteger(parsedHour) && parsedHour >= 0 && parsedHour <= 23 ? parsedHour : 8;
  const minute = Number.isInteger(parsedMinute) && parsedMinute >= 0 && parsedMinute <= 59 ? parsedMinute : 0;

  return {
    hour: hour24 % 12 || 12,
    minute,
    period: hour24 >= 12 ? "PM" : "AM",
  };
}

function serializeTime(parts: TimeParts): string {
  let hour24 = parts.hour % 12;
  if (parts.period === "PM") hour24 += 12;
  return `${String(hour24).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}:00`;
}

export function TimePicker({
  label,
  value,
  onChange,
  error,
  required = false,
}: {
  label: string;
  value?: string | null;
  onChange: (value: string) => void;
  error?: string;
  required?: boolean;
}) {
  const messageId = useId();
  const parts = parseTime(value);

  // Lets administrators choose a business time without exposing unnecessary seconds.
  function update(next: Partial<TimeParts>) {
    onChange(serializeTime({ ...parts, ...next }));
  }

  return (
    <fieldset className="block">
      <legend className="mb-1.5 text-xs font-semibold text-slate-700">
        {label}
        {required ? <span className="ml-1 text-rose-600" aria-label="required">*</span> : null}
      </legend>
      <div
        className={`flex min-h-10 items-center overflow-hidden rounded-md border bg-white transition-colors focus-within:border-signal-600 focus-within:ring-2 focus-within:ring-signal-100 ${error ? "border-rose-400 ring-2 ring-rose-100" : "border-slate-300"}`}
      >
        <Clock3 className="ml-3 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
        <select
          className="min-h-10 min-w-0 flex-1 cursor-pointer bg-transparent px-2 text-center text-sm font-semibold text-ink outline-none"
          aria-label={`${label} hour`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? messageId : undefined}
          value={parts.hour}
          onChange={(event) => update({ hour: Number(event.target.value) })}
        >
          {hours.map((hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}</option>)}
        </select>
        <span className="font-bold text-slate-400" aria-hidden="true">:</span>
        <select
          className="min-h-10 min-w-0 flex-1 cursor-pointer bg-transparent px-2 text-center text-sm font-semibold text-ink outline-none"
          aria-label={`${label} minute`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? messageId : undefined}
          value={parts.minute}
          onChange={(event) => update({ minute: Number(event.target.value) })}
        >
          {minutes.map((minute) => <option key={minute} value={minute}>{String(minute).padStart(2, "0")}</option>)}
        </select>
        <select
          className="min-h-10 cursor-pointer border-l border-slate-300 bg-slate-50 px-3 text-sm font-bold text-ocean-700 outline-none"
          aria-label={`${label} period`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? messageId : undefined}
          value={parts.period}
          onChange={(event) => update({ period: event.target.value as Period })}
        >
          <option value="AM">AM</option>
          <option value="PM">PM</option>
        </select>
      </div>
      {error ? <span id={messageId} className="mt-1.5 block text-xs font-semibold leading-relaxed text-rose-600">{error}</span> : null}
    </fieldset>
  );
}
