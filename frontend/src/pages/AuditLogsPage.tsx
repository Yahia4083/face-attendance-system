import { CalendarClock, Eye, FilterX, MonitorCheck, Search, ShieldCheck, Target, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { listAuditLogs, type AuditLogQuery } from "../api/auditLogs";
import { Button } from "../components/common/Button";
import { Card, SectionHeader } from "../components/common/Card";
import { Field, FormErrorSummary, inputClass } from "../components/common/Form";
import { Modal } from "../components/common/Modal";
import { PageHeader } from "../components/common/PageHeader";
import { Pagination } from "../components/common/Pagination";
import { ErrorState, LoadingState } from "../components/common/State";
import { DataTable } from "../components/common/Table";
import { useAsync } from "../hooks/useAsync";
import type { AuditActor, AuditLogItem, AuditMetadata } from "../types/audit";
import {
  auditActionCategory,
  auditCategoryClass,
  auditCategoryLabel,
  formatAuditAction,
  formatAuditDateTime,
  formatAuditMetadataKey,
} from "../utils/auditFormatters";
import { formatDate } from "../utils/dateTime";

type AuditFilters = {
  date_from: string;
  date_to: string;
  action: string;
  actor: string;
  entity_type: string;
};

const emptyFilters: AuditFilters = {
  date_from: "",
  date_to: "",
  action: "",
  actor: "",
  entity_type: "",
};

function requestParams(filters: AuditFilters, page: number, pageSize: number): AuditLogQuery {
  return {
    page,
    page_size: pageSize,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    action: filters.action || undefined,
    actor: filters.actor.trim() || undefined,
    entity_type: filters.entity_type || undefined,
  };
}

function ActionBadge({ action }: { action: string }) {
  const category = auditActionCategory(action);
  return (
    <div>
      <p className="font-semibold text-ink">{formatAuditAction(action)}</p>
      <span className={`mt-1.5 inline-flex rounded px-2.5 py-1 text-[0.7rem] font-semibold ring-1 ${auditCategoryClass(category)}`}>
        {auditCategoryLabel(category)}
      </span>
    </div>
  );
}

function formatScalar(value: string | number | boolean | null): string {
  if (value === null) return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function metadataObject(value?: AuditMetadata): Record<string, AuditMetadata> | null {
  if (!value || Array.isArray(value) || typeof value !== "object") return null;
  return value;
}

function metadataField(item: AuditLogItem, key: string): AuditMetadata | undefined {
  return metadataObject(item.current_values)?.[key] ?? metadataObject(item.previous_values)?.[key];
}

const hiddenMetadataKeys = new Set([
  "id",
  "recognition_model_name",
  "detector_backend",
  "model_name",
  "model_path",
  "frames_analyzed",
  "confidence",
  "created_at",
  "updated_at",
  "ip_address",
]);

const hiddenMetadataFragments = [
  "password",
  "token",
  "secret",
  "embedding",
  "image_path",
  "database_url",
  "similarity",
  "threshold",
];

function shouldDisplayMetadataField(
  key: string,
  previous: AuditMetadata | undefined,
  current: AuditMetadata | undefined,
): boolean {
  const normalized = key.toLowerCase();
  const displayedValue = current === undefined ? previous : current;
  if (hiddenMetadataKeys.has(normalized) || normalized.endsWith("_id")) return false;
  if (hiddenMetadataFragments.some((fragment) => normalized.includes(fragment))) return false;
  if (displayedValue === false && previous !== true) return false;
  if (displayedValue === 0 && normalized.endsWith("_minutes") && previous !== undefined && previous !== null && previous !== 0) return true;
  if (displayedValue === 0 && normalized.endsWith("_minutes")) return false;
  return true;
}

function metadataValuesMatch(left: AuditMetadata | undefined, right: AuditMetadata | undefined): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

const liveKioskActions = new Set([
  "LIVENESS_VERIFICATION_FAILED",
  "LIVE_ATTENDANCE_REJECTED",
]);

function isLiveKioskEvent(item: AuditLogItem): boolean {
  return metadataField(item, "source") === "LIVE_KIOSK" || liveKioskActions.has(item.action);
}

function resolvedPerformer(item: AuditLogItem): AuditActor {
  if (item.performed_by) return item.performed_by;

  if (isLiveKioskEvent(item) && ["ATTENDANCE_CHECK_IN", "ATTENDANCE_CHECK_OUT"].includes(item.action)) {
    const employeeName = metadataField(item, "employee_name");
    const employeeNumber = metadataField(item, "employee_number");
    const employeeId = metadataField(item, "employee_id");
    if (typeof employeeName === "string") {
      return {
        id: typeof employeeId === "number" ? employeeId : null,
        name: employeeName,
        employee_number: typeof employeeNumber === "string" ? employeeNumber : null,
        kind: "EMPLOYEE",
      };
    }
  }

  if (isLiveKioskEvent(item)) {
    return { id: null, name: "Live kiosk terminal", kind: "SYSTEM" };
  }
  return item.actor;
}

function formatMetadataValue(key: string, value: AuditMetadata | undefined): React.ReactNode {
  if (value === undefined) return <span className="text-slate-400">—</span>;
  if (value === null) return <span className="text-slate-400">Not set</span>;
  if (typeof value === "string" && key.endsWith("_at")) {
    const formatted = formatAuditDateTime(value);
    return `${formatted.date}${formatted.time ? `, ${formatted.time}` : ""}`;
  }
  if (typeof value === "string" && (key.endsWith("_date") || key === "date")) {
    return formatDate(value);
  }
  if (typeof value === "string" && ["status", "source", "challenge_type", "request_type"].includes(key)) {
    return formatAuditMetadataKey(value);
  }
  if (typeof value === "number" && key.endsWith("_minutes")) return `${value} min`;
  if (typeof value === "object") return <MetadataValue value={value} depth={1} />;
  return formatScalar(value);
}

const metadataPriority = [
  "employee_name",
  "employee_number",
  "employee_id",
  "schedule_date",
  "schedule_template_name",
  "status",
  "scheduled_start_datetime",
  "scheduled_end_datetime",
  "check_in_at",
  "check_out_at",
  "is_late",
  "late_minutes",
  "is_early_departure",
  "early_departure_minutes",
  "is_missing_checkout",
  "is_unscheduled",
  "source",
  "failure_reason",
  "challenge_type",
  "frames_analyzed",
  "confidence",
];

function sortedMetadataKeys(previous?: AuditMetadata, current?: AuditMetadata): string[] {
  const previousValues = metadataObject(previous) ?? {};
  const currentValues = metadataObject(current) ?? {};
  const currentKeys = Object.keys(currentValues).filter((key) => (
    shouldDisplayMetadataField(key, previousValues[key], currentValues[key])
  ));
  const keys = currentKeys.length
    ? currentKeys
    : Object.keys(previousValues).filter((key) => shouldDisplayMetadataField(key, previousValues[key], undefined));
  const priority = new Map(metadataPriority.map((key, index) => [key, index]));
  return keys.sort((left, right) => {
    const leftPriority = priority.get(left) ?? metadataPriority.length;
    const rightPriority = priority.get(right) ?? metadataPriority.length;
    return leftPriority - rightPriority || left.localeCompare(right);
  });
}

function MetadataValue({ value, depth = 0 }: { value: AuditMetadata; depth?: number }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-slate-500">None</span>;
    return (
      <ul className="space-y-2">
        {value.map((item, index) => (
          <li key={index} className="rounded-md border border-slate-200 bg-white p-3">
            <MetadataValue value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value).filter(([key, item]) => shouldDisplayMetadataField(key, undefined, item));
    if (!entries.length) return <span className="text-slate-500">No values</span>;
    return (
      <dl className={`grid gap-x-4 gap-y-3 ${depth ? "" : "sm:grid-cols-2"}`}>
        {entries.map(([key, item]) => (
          <div key={key} className="min-w-0 rounded-md border border-slate-200 bg-white p-3">
            <dt className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">
              {formatAuditMetadataKey(key)}
            </dt>
            <dd className="mt-1 break-words text-sm font-medium text-slate-800">
              <MetadataValue value={item} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span>{formatScalar(value)}</span>;
}

function AuditValueComparison({ previous, current }: { previous?: AuditMetadata; current?: AuditMetadata }) {
  const previousValues = metadataObject(previous);
  const currentValues = metadataObject(current);
  const keys = sortedMetadataKeys(previous, current);

  return (
    <section aria-labelledby="recorded-values-title">
      <div className="mb-3">
        <h3 id="recorded-values-title" className="font-display text-base font-bold text-ink">Recorded event values</h3>
        <p className="mt-1 text-sm text-slate-500">Only operationally useful fields are shown, aligned with their value before the event when available.</p>
      </div>
      {!keys.length ? (
        <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
          No values recorded.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-200">
          <div className="hidden grid-cols-[minmax(10rem,0.8fr)_1fr_1fr] bg-slate-100 px-4 py-3 text-xs font-bold uppercase tracking-[0.08em] text-slate-500 md:grid">
            <span>Field</span>
            <span>Previous value</span>
            <span>Recorded value</span>
          </div>
          <div className="divide-y divide-slate-200">
            {keys.map((key) => (
              <div key={key} className="grid gap-3 bg-white px-4 py-3.5 md:grid-cols-[minmax(10rem,0.8fr)_1fr_1fr] md:items-start">
                <p className="text-xs font-bold uppercase tracking-[0.07em] text-slate-500">{formatAuditMetadataKey(key)}</p>
                <div>
                  <p className="mb-1 text-[0.68rem] font-bold uppercase tracking-wide text-slate-400 md:hidden">Previous value</p>
                  <div className="break-words text-sm font-medium text-slate-700">
                    {formatMetadataValue(
                      key,
                      metadataValuesMatch(previousValues?.[key], currentValues?.[key]) ? undefined : previousValues?.[key],
                    )}
                  </div>
                </div>
                <div className="rounded-lg bg-emerald-50/70 px-3 py-2 md:-my-2">
                  <p className="mb-1 text-[0.68rem] font-bold uppercase tracking-wide text-emerald-700 md:hidden">Recorded value</p>
                  <div className="break-words text-sm font-semibold text-slate-900">{formatMetadataValue(key, currentValues?.[key])}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function AuditLogsPage() {
  const [draftFilters, setDraftFilters] = useState<AuditFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<AuditFilters>(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [filterErrors, setFilterErrors] = useState<string[]>([]);
  const [selected, setSelected] = useState<AuditLogItem | null>(null);

  const logs = useAsync(
    () => listAuditLogs(requestParams(appliedFilters, page, pageSize)),
    [appliedFilters, page, pageSize],
  );

  const hasAppliedFilters = useMemo(
    () => Object.values(appliedFilters).some(Boolean),
    [appliedFilters],
  );

  function updateFilter(key: keyof AuditFilters, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
    setFilterErrors([]);
  }

  function applyFilters() {
    if (draftFilters.date_from && draftFilters.date_to && draftFilters.date_from > draftFilters.date_to) {
      setFilterErrors(["Start date cannot be later than end date."]);
      return;
    }
    setAppliedFilters({ ...draftFilters, actor: draftFilters.actor.trim() });
    setFilterErrors([]);
    setPage(1);
  }

  function clearFilters() {
    setDraftFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setFilterErrors([]);
    setPage(1);
  }

  const columns = [
    {
      header: "Date & Time",
      className: "min-w-40",
      render: (item: AuditLogItem) => {
        const value = formatAuditDateTime(item.created_at);
        return (
          <div>
            <p className="font-semibold text-ink">{value.date}</p>
            <p className="mt-1 text-xs text-slate-500">{value.time}</p>
          </div>
        );
      },
    },
    {
      header: "Performed By",
      className: "min-w-52",
      render: (item: AuditLogItem) => {
        const performer = resolvedPerformer(item);
        const kioskEvent = isLiveKioskEvent(item);
        return (
          <div>
            <p className="font-semibold text-ink">{performer.name}</p>
            <p className="mt-1 text-xs text-slate-500">
              {performer.employee_number
                ? `Employee ${performer.employee_number}`
                : performer.email ?? (performer.kind === "SYSTEM" ? "Automated system action" : `User #${performer.id ?? "unknown"}`)}
            </p>
            {kioskEvent ? (
              <p className="mt-1 text-xs font-medium text-sky-700">Terminal authorized by {item.actor.name}</p>
            ) : null}
          </div>
        );
      },
    },
    {
      header: "Action",
      className: "min-w-56",
      render: (item: AuditLogItem) => <ActionBadge action={item.action} />,
    },
    {
      header: "Target",
      className: "min-w-56",
      render: (item: AuditLogItem) => (
        <div>
          <p className="font-semibold text-ink">{item.target.label}</p>
          <p className="mt-1 text-xs text-slate-500">{formatAuditMetadataKey(item.target.entity_type)}</p>
        </div>
      ),
    },
    {
      header: "Details",
      className: "w-32",
      render: (item: AuditLogItem) => item.has_details ? (
        <Button size="sm" variant="secondary" onClick={() => setSelected(item)} aria-label={`View details for audit log ${item.id}`}>
          <Eye className="h-4 w-4" aria-hidden="true" />
          View
        </Button>
      ) : (
        <span className="text-xs text-slate-400">No details</span>
      ),
    },
  ];
  const selectedPerformer = selected ? resolvedPerformer(selected) : undefined;
  const selectedIsKioskEvent = selected ? isLiveKioskEvent(selected) : false;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administration"
        title="Audit Logs"
        description="Review important administrative and system activity. Audit history is read-only and cannot be changed from this portal."
      />

      <Card>
        <SectionHeader
          title="Filter audit activity"
          description="Choose your filters, then apply them when you are ready. Searches are performed securely on the server."
        />
        <FormErrorSummary messages={filterErrors} />
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <Field label="Date from" hint="Uses the Africa/Tripoli business date.">
            <input className={inputClass} type="date" value={draftFilters.date_from} onChange={(event) => updateFilter("date_from", event.target.value)} />
          </Field>
          <Field label="Date to" hint="Includes all activity on this date.">
            <input className={inputClass} type="date" value={draftFilters.date_to} onChange={(event) => updateFilter("date_to", event.target.value)} />
          </Field>
          <Field label="Action">
            <select className={inputClass} value={draftFilters.action} onChange={(event) => updateFilter("action", event.target.value)}>
              <option value="">All actions</option>
              {(logs.data?.available_actions ?? []).map((action) => (
                <option key={action} value={action}>{formatAuditAction(action)}</option>
              ))}
            </select>
          </Field>
          <Field label="Performed by" hint="Search by employee name, number, email, user ID, or System.">
            <input
              className={inputClass}
              value={draftFilters.actor}
              onChange={(event) => updateFilter("actor", event.target.value)}
              placeholder="Name or email"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  applyFilters();
                }
              }}
            />
          </Field>
          <Field label="Target type">
            <select className={inputClass} value={draftFilters.entity_type} onChange={(event) => updateFilter("entity_type", event.target.value)}>
              <option value="">All target types</option>
              {(logs.data?.available_entity_types ?? []).map((entityType) => (
                <option key={entityType} value={entityType}>{formatAuditMetadataKey(entityType)}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button onClick={applyFilters}>
            <Search className="h-4 w-4" aria-hidden="true" />
            Apply Filters
          </Button>
          <Button variant="secondary" onClick={clearFilters} disabled={!hasAppliedFilters && !Object.values(draftFilters).some(Boolean)}>
            <FilterX className="h-4 w-4" aria-hidden="true" />
            Clear Filters
          </Button>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Recorded activity"
          description={logs.data ? `${logs.data.total} matching event${logs.data.total === 1 ? "" : "s"}. Newest activity appears first.` : "Newest activity appears first."}
          action={(
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-600">
              Rows
              <select
                className={`${inputClass} min-h-9 w-24 py-1.5`}
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(1);
                }}
                aria-label="Audit logs per page"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          )}
        />

        {logs.loading ? <LoadingState label="Loading audit logs..." /> : null}
        {!logs.loading && logs.error ? (
          <div className="space-y-3">
            <ErrorState message="Audit logs could not be loaded. Please try again." />
            <Button variant="secondary" onClick={logs.refresh}>Try Again</Button>
          </div>
        ) : null}
        {!logs.loading && !logs.error && logs.data ? (
          <>
            <DataTable
              columns={columns}
              rows={logs.data.items}
              rowKey={(item) => item.id}
              caption="Administrative and system audit activity"
              emptyTitle={hasAppliedFilters ? "No matching audit activity" : "No audit activity found"}
              empty={hasAppliedFilters ? "No audit logs match the selected filters." : "Important administrative and system events will appear here."}
            />
            <Pagination page={logs.data.page} pageSize={logs.data.page_size} total={logs.data.total} onPageChange={setPage} />
          </>
        ) : null}
      </Card>

      <Modal
        open={Boolean(selected)}
        title="Audit Log Details"
        description="Safe historical information recorded for this event. Sensitive values are redacted by the server."
        onClose={() => setSelected(null)}
        size="xl"
        footer={<div className="flex justify-end"><Button variant="secondary" onClick={() => setSelected(null)}>Close</Button></div>}
      >
        {selected ? (
          <div className="space-y-6">
            <div className="overflow-hidden rounded-md bg-slate-950 text-white shadow-sm">
              <div className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`inline-flex rounded px-2.5 py-1 text-[0.7rem] font-semibold ring-1 ${auditCategoryClass(auditActionCategory(selected.action))}`}>
                      {auditCategoryLabel(auditActionCategory(selected.action))}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">Audit event #{selected.id}</span>
                  </div>
                  <p className="mt-3 font-display text-xl font-bold">{formatAuditAction(selected.action)}</p>
                </div>
                <div className="flex items-center gap-3 rounded-md bg-white/10 px-4 py-3 sm:text-right">
                  <CalendarClock className="h-5 w-5 text-sky-300" aria-hidden="true" />
                  <div>
                    <p className="font-semibold">{formatAuditDateTime(selected.created_at).date}</p>
                    <p className="text-xs text-slate-300">{formatAuditDateTime(selected.created_at).time} - Africa/Tripoli</p>
                  </div>
                </div>
              </div>
            </div>

            <section aria-labelledby="event-participants-title">
              <h3 id="event-participants-title" className="mb-3 font-display text-base font-bold text-ink">Event overview</h3>
              <div className={`grid gap-3 ${selectedIsKioskEvent ? "md:grid-cols-3" : "md:grid-cols-2"}`}>
                <div className="flex items-start gap-3 rounded-md border border-slate-200 bg-white p-4">
                  <div className="rounded-md bg-sky-50 p-2.5 text-sky-700">
                    {selectedPerformer?.kind === "EMPLOYEE" ? <UserRound className="h-5 w-5" /> : <MonitorCheck className="h-5 w-5" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{selectedIsKioskEvent ? "Employee / event source" : "Performed by"}</p>
                    <p className="mt-1 font-semibold text-ink">{selectedPerformer?.name}</p>
                    <p className="mt-1 break-words text-xs text-slate-500">
                      {selectedPerformer?.employee_number
                        ? `Employee ${selectedPerformer.employee_number}`
                        : selectedPerformer?.email ?? (selectedPerformer?.kind === "SYSTEM" ? "Automated camera terminal" : selectedPerformer?.kind)}
                    </p>
                  </div>
                </div>

                {selectedIsKioskEvent ? (
                  <div className="flex items-start gap-3 rounded-md border border-sky-200 bg-sky-50/70 p-4">
                    <div className="rounded-md bg-white p-2.5 text-sky-700 shadow-sm"><ShieldCheck className="h-5 w-5" /></div>
                    <div className="min-w-0">
                      <p className="text-xs font-bold uppercase tracking-[0.08em] text-sky-700">Terminal authorized by</p>
                      <p className="mt-1 font-semibold text-ink">{selected.actor.name}</p>
                      <p className="mt-1 text-xs text-slate-500">Administrator account</p>
                    </div>
                  </div>
                ) : null}

                <div className="flex items-start gap-3 rounded-md border border-slate-200 bg-white p-4">
                  <div className="rounded-md bg-amber-50 p-2.5 text-amber-700"><Target className="h-5 w-5" /></div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Target</p>
                    <p className="mt-1 font-semibold text-ink">{selected.target.label}</p>
                    <p className="mt-1 text-xs text-slate-500">{formatAuditMetadataKey(selected.target.entity_type)}</p>
                  </div>
                </div>
              </div>
            </section>

            {selectedIsKioskEvent ? (
              <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm leading-relaxed text-sky-900">
                The employee or visitor performed the camera event. The administrator shown above only authorized the kiosk session and did not perform the attendance action.
              </div>
            ) : null}

            <AuditValueComparison previous={selected.previous_values} current={selected.current_values} />

            <div className="flex items-start gap-3 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              <p>Sensitive passwords, tokens, face embeddings, and raw image data are excluded from this view.</p>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
