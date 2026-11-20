export type AuditMetadata =
  | null
  | string
  | number
  | boolean
  | AuditMetadata[]
  | { [key: string]: AuditMetadata };

export type AuditActor = {
  id?: number | null;
  name: string;
  email?: string | null;
  kind: "USER" | "SYSTEM" | "UNKNOWN" | string;
  employee_number?: string | null;
};

export type AuditTarget = {
  entity_type: string;
  entity_id?: number | null;
  label: string;
};

export type AuditLogItem = {
  id: number;
  action: string;
  actor: AuditActor;
  performed_by?: AuditActor | null;
  target: AuditTarget;
  created_at: string;
  previous_values?: AuditMetadata;
  current_values?: AuditMetadata;
  has_details: boolean;
};

export type AuditLogListResponse = {
  items: AuditLogItem[];
  page: number;
  page_size: number;
  total: number;
  timezone: string;
  available_actions: string[];
  available_entity_types: string[];
};
