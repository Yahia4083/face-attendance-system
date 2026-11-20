import { useEffect, useState } from "react";
import { listSystemSettings, updateSystemSetting } from "../api/settings";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { ConfirmationDialog } from "../components/common/ConfirmationDialog";
import { inputClass } from "../components/common/Form";
import { PageHeader } from "../components/common/PageHeader";
import { ErrorState, LoadingState } from "../components/common/State";
import { useToast } from "../components/common/Toast";
import { useAsync } from "../hooks/useAsync";
import type { SystemSetting } from "../types/api";
import { parseApiError } from "../utils/apiErrors";
import { formatDateTime } from "../utils/dateTime";

// Provides the automatic audit reason for inline setting updates.
const AUTO_REASON = "Updated from System Settings page.";

const integerOptions: Record<string, { value: number; label: string }[]> = {
  // Defines preset choices for integer settings.
  JUSTIFICATION_MONTHLY_LIMIT: [
    { value: 0, label: "No justifications allowed" },
    { value: 1, label: "1 request per month" },
    { value: 2, label: "2 requests per month" },
    { value: 3, label: "3 requests per month" },
    { value: 4, label: "4 requests per month" },
    { value: 5, label: "5 requests per month" },
    { value: 10, label: "10 requests per month" },
    { value: 15, label: "15 requests per month" },
    { value: 31, label: "Maximum monthly allowance" },
  ],
};

function settingValueText(value: unknown, setting?: SystemSetting) {
  if (setting) {
    const optionLabel = integerOptions[setting.key]?.find((option) => option.value === Number(value))?.label;
    if (optionLabel) return optionLabel;
  }
  if (typeof value === "boolean") return value ? "Enabled" : "Disabled";
  return String(value);
}

function validateIntegerSetting(setting: SystemSetting, value: number): string | null {
  // Validates integer setting values before saving.
  if (!Number.isInteger(value)) return `${setting.display_name} must be a whole number.`;
  if (setting.key === "ATTENDANCE_PROCESSING_DELAY_MINUTES" && (value < 0 || value > 1440)) {
    return "Attendance processing delay must be between 0 and 1440 minutes.";
  }
  if (setting.key === "MISSING_CHECKOUT_DELAY_MINUTES" && (value < 0 || value > 1440)) {
    return "Missing checkout delay must be between 0 and 1440 minutes.";
  }
  if (setting.key === "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES" && (value < 0 || value > 720)) {
    return "Early check-in window must be between 0 and 720 minutes.";
  }
  if (setting.key === "OVERTIME_MINIMUM_MINUTES" && (value < 1 || value > 720)) {
    return "Overtime minimum must be between 1 and 720 minutes.";
  }
  if (setting.key === "REPORT_EXPORT_MAX_DATE_RANGE_DAYS" && (value < 1 || value > 3660)) {
    return "Report export maximum range must be between 1 and 3660 days.";
  }
  if (setting.key === "JUSTIFICATION_MONTHLY_LIMIT" && (value < 0 || value > 31)) {
    return "Monthly justification limit must be between 0 and 31.";
  }
  return null;
}

function settingHelperLines(setting: SystemSetting): string[] {
  if (setting.key === "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES") {
    return [
      "Check-ins earlier than this window or after the scheduled end are recorded as unscheduled.",
      "Changes affect future attendance only.",
    ];
  }
  if (setting.key === "MISSING_CHECKOUT_DELAY_MINUTES") {
    return [
      "Open check-ins remain active during this post-shift window so employees can complete overtime before checking out.",
      "The recommended four-hour overtime window is 240 minutes.",
    ];
  }
  if (setting.key === "JUSTIFICATION_MONTHLY_LIMIT") {
    return [
      "Maximum number of justification requests each employee can submit per month. Rejected requests still count.",
      "Changes affect future submissions only.",
    ];
  }
  return [];
}

function InlineSettingControl({
  setting,
  onSaved,
}: {
  setting: SystemSetting;
  onSaved: () => void;
}) {
  const { notify } = useToast();
  const [value, setValue] = useState(setting.value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingValue, setPendingValue] = useState<{ value: unknown } | null>(null);

  useEffect(() => {
    setValue(setting.value);
    setError(null);
    setPendingValue(null);
  }, [setting.key, setting.value]);

  async function saveValue(nextValue: unknown) {
    if (!setting.editable_by_admin) return;
    setSaving(true);
    setError(null);
    try {
      await updateSystemSetting(setting.key, {
        value: nextValue,
        // Sends the automatic audit reason with the setting update.
        reason: AUTO_REASON,
      });
      notify("System setting updated. Future operations will use the new value.", "success");
      setPendingValue(null);
      onSaved();
    } catch (err) {
      const parsed = parseApiError(err);
      setError(parsed.summary);
      setValue(setting.value);
      notify(parsed.summary, "error");
    } finally {
      setSaving(false);
    }
  }

  if (!setting.editable_by_admin) {
    return (
      <div className="space-y-2">
        <input
          className={`${inputClass} bg-slate-50 text-slate-600`}
          value={settingValueText(setting.value, setting)}
          disabled
          readOnly
          aria-label={setting.display_name}
        />
        <p className="text-xs font-semibold text-slate-500">Managed by the system.</p>
      </div>
    );
  }

  if (setting.data_type === "BOOLEAN") {
    const checked = Boolean(value);
    return (
      <>
      {/* Renders an inline switch for boolean settings. */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={saving}
          onClick={() => {
            const next = !checked;
            setValue(next);
            setPendingValue({ value: next });
          }}
          className={`relative inline-flex h-8 w-16 items-center rounded-full border-2 border-transparent transition-colors ${checked ? "bg-ocean-600" : "bg-slate-300"} disabled:cursor-not-allowed disabled:opacity-60`}
          aria-label={`Toggle ${setting.display_name}`}
        >
          <span className={`inline-block h-6 w-6 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-8" : "translate-x-0"}`} />
        </button>
        <span className="text-sm font-semibold text-slate-600">{checked ? "Enabled" : "Disabled"}</span>
      </div>
      <ConfirmationDialog
        open={Boolean(pendingValue)}
        title={`Update ${setting.display_name}?`}
        description="This policy change affects future operations only and will be recorded in the audit log."
        confirmLabel="Confirm change"
        loading={saving}
        onClose={() => {
          if (saving) return;
          setPendingValue(null);
          setValue(setting.value);
        }}
        onConfirm={async () => {
          if (pendingValue) await saveValue(pendingValue.value);
        }}
      />
      </>
    );
  }

  if (setting.data_type === "INTEGER") {
    const numericValue = Number(value);
    // Renders an inline selector or numeric input for integer settings.
    const options = integerOptions[setting.key];
    return (
      <>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {options ? (
          <select
            className={`${inputClass} w-80 max-w-full`}
            value={String(numericValue)}
            disabled={saving}
            onChange={(event) => {
              const next = Number(event.target.value);
              setValue(next);
              setPendingValue({ value: next });
            }}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <>
            <input
              className={`${inputClass} w-36`}
              type="number"
              value={String(value ?? "")}
              disabled={saving}
              onChange={(event) => {
                setValue(event.target.value);
                setError(null);
              }}
            />
            <Button
              variant="secondary"
              disabled={saving}
              onClick={() => {
                const next = Number(value);
                const localError = validateIntegerSetting(setting, next);
                if (localError) {
                  setError(localError);
                  return;
                }
                setPendingValue({ value: next });
              }}
              loading={saving}
              loadingLabel="Saving..."
            >
              Save
            </Button>
          </>
        )}
        {error ? <span className="text-xs font-semibold text-rose-600">{error}</span> : null}
      </div>
      <ConfirmationDialog
        open={Boolean(pendingValue)}
        title={`Update ${setting.display_name}?`}
        description="This policy change affects future operations only and will be recorded in the audit log."
        confirmLabel="Confirm change"
        loading={saving}
        onClose={() => {
          if (saving) return;
          setPendingValue(null);
          setValue(setting.value);
        }}
        onConfirm={async () => {
          if (pendingValue) await saveValue(pendingValue.value);
        }}
      />
      </>
    );
  }

  return <span className="text-sm font-semibold text-slate-600">{settingValueText(setting.value)}</span>;
}

export function SettingsPage() {
  const settings = useAsync(() => listSystemSettings(), []);
  // Filters the settings list to operational policy groups.
  const visibleSettings = (settings.data?.items ?? []).filter(
    (item) => item.category !== "ORGANIZATION" && item.category !== "REPORTING",
  );

  const grouped = visibleSettings.reduce<Record<string, SystemSetting[]>>((acc, item) => {
    acc[item.category] = [...(acc[item.category] ?? []), item];
    return acc;
  }, {});

  return (
    <div className="page-stack">
      <PageHeader
        title="System Settings"
        description="Manage safe runtime business policies. Every change is audit logged and affects future operations only."
      />

      {settings.loading ? (
        <LoadingState />
      ) : settings.error ? (
        <ErrorState message={settings.error} />
      ) : (
        Object.entries(grouped).map(([category, items]) => (
          <Card key={category}>
            <SectionHeader title={category.replaceAll("_", " ")} description="Runtime policy controls. Protected values remain read-only." />
            <div className="divide-y divide-slate-200 border-y border-slate-300">
              {items.map((item) => (
                <div key={item.key} className="px-1 py-4 sm:px-2">
                  <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-start">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-ink">{item.display_name}</h3>
                      </div>
                      <p className="mt-1 text-sm text-slate-500">{item.description}</p>
                      {settingHelperLines(item).map((line) => (
                        <p key={line} className="mt-2 text-xs font-semibold text-slate-600">
                          {line}
                        </p>
                      ))}
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        <span>Default: {settingValueText(item.default_value, item)}</span>
                        <span>Source: <strong className="font-semibold text-slate-700">{item.source.replaceAll("_", " ")}</strong></span>
                        <span>Updated: {formatDateTime(item.updated_at)}</span>
                      </div>
                      {item.future_requests_only && item.key !== "JUSTIFICATION_MONTHLY_LIMIT" ? (
                        <p className="mt-2 text-xs font-semibold text-ocean-700">Changes affect future operations only.</p>
                      ) : null}
                    </div>
                    <div className="min-w-48 lg:pt-0.5">
                      <InlineSettingControl setting={item} onSaved={settings.refresh} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
