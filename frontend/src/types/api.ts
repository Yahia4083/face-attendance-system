export type UserRole = "ADMIN" | "EMPLOYEE";

export type CurrentUser = {
  id: number;
  email: string;
  role: UserRole | string;
  is_active: boolean;
  must_change_password: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: CurrentUser;
};

export type Paginated<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type AttendanceStatus =
  | "PRESENT"
  | "LATE"
  | "EARLY_DEPARTURE"
  | "MISSING_CHECKOUT"
  | "ABSENT"
  | "UNSCHEDULED";

export type RequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export type AttendanceCorrection = {
  id: number;
  attendance_record_id: number;
  original_status: string;
  corrected_status: string;
  reason: string;
  corrected_by_user_id: number;
  corrected_at: string;
  created_at: string;
  message?: string | null;
};

export type AttendanceRecord = {
  id: number;
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  employee_schedule_id?: number | null;
  schedule_template_id?: number | null;
  schedule_template_name?: string | null;
  schedule_date: string;
  scheduled_start_datetime?: string | null;
  scheduled_end_datetime?: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  working_hours?: number | null;
  status: AttendanceStatus | string;
  is_late: boolean;
  is_early_departure: boolean;
  is_unscheduled: boolean;
  is_missing_checkout: boolean;
  late_minutes: number;
  early_departure_minutes: number;
  has_pending_justification: boolean;
  latest_justification_status?: string | null;
  has_pending_overtime_request: boolean;
  latest_overtime_status?: string | null;
  recognition_model_name?: string | null;
  original_status: string;
  effective_status: string;
  has_admin_correction: boolean;
  latest_correction?: AttendanceCorrection | null;
  created_at: string;
  updated_at: string;
};

export type ProcessDailyAttendanceResult = {
  on_date: string;
  timezone: string;
  processed_assignments: number;
  absent_records_created: number;
  missing_checkout_records_updated: number;
  already_processed_or_unchanged: number;
  message: string;
};

export type DashboardSummary = {
  dashboard_type: string;
  organization_name: string;
  on_date: string;
  timezone: string;
  generated_at: string;
  attendance: {
    total_records: number;
    scheduled_processed_shift_count: number;
    scheduled_attended_shift_count: number;
    present_on_time_count: number;
    late_count: number;
    absent_count: number;
    early_departure_count: number;
    missing_checkout_count: number;
    unscheduled_attendance_count: number;
    open_check_in_count: number;
    attendance_rate_percentage: number | null;
  };
  requests: {
    pending_justification_count: number;
    pending_overtime_request_count: number;
    total_pending_request_count: number;
  };
  overtime: {
    approved_overtime_request_count: number;
    approved_overtime_minutes: number;
    approved_overtime_hours: number;
  };
  employees: {
    active_employee_count: number;
    active_department_count: number;
  };
  data_basis: string;
  requires_daily_processing_for_complete_absence_metrics: boolean;
};

export type DashboardAttendanceItem = {
  attendance_id: number;
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  department_id?: number | null;
  department_name?: string | null;
  schedule_date: string;
  schedule_template_name?: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  status: string;
  is_late: boolean;
  is_early_departure: boolean;
  is_missing_checkout: boolean;
  is_unscheduled: boolean;
  latest_justification_status?: string | null;
  latest_overtime_status?: string | null;
};

export type DashboardTable = Paginated<DashboardAttendanceItem> & {
  on_date: string;
  timezone: string;
  summary: {
    total_records: number;
    late_count: number;
    absent_count: number;
    missing_checkout_count: number;
    unscheduled_attendance_count: number;
  };
  data_basis: string;
  requires_daily_processing_for_complete_absence_metrics: boolean;
};

export type PendingRequestItem = {
  request_category: "JUSTIFICATION" | "OVERTIME";
  request_id: number;
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  attendance_record_id: number;
  attendance_status?: string | null;
  request_type?: string | null;
  reason?: string | null;
  requested_minutes?: number | null;
  eligible_minutes_at_submission?: number | null;
  status: RequestStatus | string;
  created_at?: string | null;
};

export type PendingRequests = Paginated<PendingRequestItem> & {
  summary: {
    pending_justification_count: number;
    pending_overtime_request_count: number;
    total_pending_request_count: number;
  };
};

export type DepartmentDashboardItem = {
  department_id: number;
  department_name: string;
  active_employee_count: number;
  total_records: number;
  scheduled_processed_shift_count: number;
  scheduled_attended_shift_count: number;
  present_on_time_count: number;
  late_count: number;
  absent_count: number;
  early_departure_count: number;
  missing_checkout_count: number;
  unscheduled_attendance_count: number;
  attendance_rate_percentage: number | null;
};

export type DashboardTrendItem = {
  date: string;
  scheduled_processed_shift_count: number;
  scheduled_attended_shift_count: number;
  present_on_time_count: number;
  late_count: number;
  absent_count: number;
  missing_checkout_count: number;
  unscheduled_attendance_count: number;
  attendance_rate_percentage: number | null;
};

export type DashboardActivity = {
  activity_type: string;
  employee_id?: number | null;
  employee_name?: string | null;
  description: string;
  occurred_at?: string | null;
  related_entity_type: string;
  related_entity_id?: number | null;
};

export type Employee = {
  id: number;
  user_id: number;
  email: string;
  department_id: number;
  department_name: string;
  full_name: string;
  employee_number: string;
  phone?: string | null;
  position?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Department = {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ScheduleTemplate = {
  id: number;
  name: string;
  description?: string | null;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
  check_in_grace_minutes: number;
  early_departure_tolerance_minutes: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type EmployeeSchedule = {
  id: number;
  employee_id: number;
  employee_name?: string | null;
  schedule_template_id: number;
  schedule_template_name?: string | null;
  effective_from: string;
  effective_to?: string | null;
  working_days: number[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type EffectiveSchedule = {
  employee_id: number;
  employee_name: string;
  on_date: string;
  has_schedule: boolean;
  working_day: boolean;
  assignment_id?: number | null;
  schedule_template_id?: number | null;
  schedule_template_name?: string | null;
  scheduled_start_datetime?: string | null;
  scheduled_end_datetime?: string | null;
  is_overnight?: boolean | null;
  check_in_grace_minutes?: number | null;
  early_departure_tolerance_minutes?: number | null;
  timezone?: string | null;
  message?: string | null;
};

export type JustificationRequest = {
  id: number;
  attendance_record_id: number;
  employee_id: number;
  employee_name?: string | null;
  request_type: string;
  reason: string;
  status: RequestStatus | string;
  reviewer_user_id?: number | null;
  reviewer_note?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  message?: string | null;
};

export type OvertimeRequest = {
  id: number;
  employee_id: number;
  employee_name?: string | null;
  attendance_record_id: number;
  requested_minutes: number;
  eligible_minutes_at_submission: number;
  approved_minutes?: number | null;
  reason?: string | null;
  status: RequestStatus | string;
  reviewer_user_id?: number | null;
  reviewer_note?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  message?: string | null;
};

export type SystemSetting = {
  key: string;
  display_name: string;
  description: string;
  category: string;
  data_type: "STRING" | "BOOLEAN" | "INTEGER" | string;
  value: unknown;
  default_value: unknown;
  source: string;
  editable_by_admin: boolean;
  future_requests_only: boolean;
  updated_at?: string | null;
  updated_by_user_id?: number | null;
};

export type ReportSummary = {
  total_records: number;
  scheduled_processed_shift_count: number;
  scheduled_attended_shift_count: number;
  present_on_time_count: number;
  late_count: number;
  absent_count: number;
  early_departure_count: number;
  missing_checkout_count: number;
  unscheduled_attendance_count: number;
  approved_overtime_minutes: number;
  approved_overtime_hours: number;
  attendance_rate_percentage: number | null;
  [key: string]: number | null | undefined;
};

export type EmployeeAttendanceSummary = {
  report_type: string;
  employee_id: number;
  employee_name?: string | null;
  employee_number?: string | null;
  department_name?: string | null;
  date_from: string;
  date_to: string;
  timezone: string;
  summary: ReportSummary;
  records: ReportRow[];
  data_basis: string;
  requires_daily_processing_for_complete_absence_metrics: boolean;
};

export type ReportRow = {
  attendance_id: number;
  employee_id?: number | null;
  employee_name?: string | null;
  employee_number?: string | null;
  department_id?: number | null;
  department_name?: string | null;
  schedule_date: string;
  schedule_template_name?: string | null;
  scheduled_start_datetime?: string | null;
  scheduled_end_datetime?: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  working_hours?: number | null;
  status: string;
  is_late?: boolean;
  is_early_departure?: boolean;
  is_unscheduled?: boolean;
  is_missing_checkout?: boolean;
  latest_justification_status?: string | null;
  latest_overtime_status?: string | null;
  approved_overtime_minutes?: number;
};
