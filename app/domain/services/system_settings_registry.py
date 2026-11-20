"""Allowlisted runtime system setting definitions."""

from app.domain.entities.system_setting import SystemSettingDefinition
from app.domain.enums.setting_category import SettingCategory
from app.domain.enums.setting_data_type import SettingDataType


SYSTEM_SETTING_DEFINITIONS: dict[str, SystemSettingDefinition] = {
    "ORGANIZATION_NAME": SystemSettingDefinition(
        key="ORGANIZATION_NAME",
        display_name="Organization Name",
        description="Display name used in reports and future user interfaces.",
        category=SettingCategory.ORGANIZATION,
        data_type=SettingDataType.STRING,
        default_value="Attendance Face Recognition System",
        editable_by_admin=True,
        env_key="APP_NAME",
        min_length=2,
        max_length=150,
    ),
    "ORGANIZATION_TIMEZONE": SystemSettingDefinition(
        key="ORGANIZATION_TIMEZONE",
        display_name="Organization Timezone",
        description="Business timezone currently used for schedules and attendance.",
        category=SettingCategory.ORGANIZATION,
        data_type=SettingDataType.STRING,
        default_value="Africa/Tripoli",
        editable_by_admin=False,
        env_key="APP_TIMEZONE",
    ),
    "ALLOW_UNSCHEDULED_ATTENDANCE": SystemSettingDefinition(
        key="ALLOW_UNSCHEDULED_ATTENDANCE",
        display_name="Allow Unscheduled Attendance",
        description="Allow future check-ins when no active work schedule exists.",
        category=SettingCategory.ATTENDANCE,
        data_type=SettingDataType.BOOLEAN,
        default_value=True,
        editable_by_admin=True,
        env_key="ALLOW_UNSCHEDULED_ATTENDANCE",
    ),
    "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES": SystemSettingDefinition(
        key="ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES",
        display_name="Early Check-in Window Minutes",
        description=(
            "Maximum number of minutes before a scheduled shift that a future "
            "check-in may be linked to that shift. Earlier or post-shift check-ins "
            "are treated as unscheduled."
        ),
        category=SettingCategory.ATTENDANCE,
        data_type=SettingDataType.INTEGER,
        default_value=60,
        editable_by_admin=True,
        env_key="ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES",
        min_value=0,
        max_value=720,
    ),
    "ATTENDANCE_PROCESSING_DELAY_MINUTES": SystemSettingDefinition(
        key="ATTENDANCE_PROCESSING_DELAY_MINUTES",
        display_name="Attendance Processing Delay Minutes",
        description=(
            "Delay after scheduled shift end before daily processing can create "
            "ABSENT records when no check-in exists."
        ),
        category=SettingCategory.ATTENDANCE,
        data_type=SettingDataType.INTEGER,
        default_value=30,
        editable_by_admin=True,
        env_key="ATTENDANCE_PROCESSING_DELAY_MINUTES",
        min_value=0,
        max_value=1440,
    ),
    "MISSING_CHECKOUT_DELAY_MINUTES": SystemSettingDefinition(
        key="MISSING_CHECKOUT_DELAY_MINUTES",
        display_name="Missing Checkout Delay Minutes",
        description=(
            "Maximum post-shift window for overtime or a delayed checkout before an "
            "open attendance record is marked MISSING_CHECKOUT."
        ),
        category=SettingCategory.ATTENDANCE,
        data_type=SettingDataType.INTEGER,
        default_value=240,
        editable_by_admin=True,
        env_key="MISSING_CHECKOUT_DELAY_MINUTES",
        min_value=0,
        max_value=1440,
    ),
    "OVERTIME_MINIMUM_MINUTES": SystemSettingDefinition(
        key="OVERTIME_MINIMUM_MINUTES",
        display_name="Overtime Minimum Minutes",
        description="Minimum eligible overtime duration required for future overtime requests.",
        category=SettingCategory.OVERTIME,
        data_type=SettingDataType.INTEGER,
        default_value=30,
        editable_by_admin=True,
        env_key="OVERTIME_MINIMUM_MINUTES",
        min_value=1,
        max_value=720,
    ),
    "JUSTIFICATION_MONTHLY_LIMIT": SystemSettingDefinition(
        key="JUSTIFICATION_MONTHLY_LIMIT",
        display_name="Monthly Justification Limit",
        description=(
            "Maximum number of justification requests an employee may submit "
            "for attendance records in one business month. Zero disables new submissions."
        ),
        category=SettingCategory.JUSTIFICATION,
        data_type=SettingDataType.INTEGER,
        default_value=3,
        editable_by_admin=True,
        env_key="JUSTIFICATION_MONTHLY_LIMIT",
        min_value=0,
        max_value=31,
    ),
    "REPORT_EXPORT_MAX_DATE_RANGE_DAYS": SystemSettingDefinition(
        key="REPORT_EXPORT_MAX_DATE_RANGE_DAYS",
        display_name="Report Export Maximum Date Range Days",
        description="Maximum date range allowed for future attendance report exports.",
        category=SettingCategory.REPORTING,
        data_type=SettingDataType.INTEGER,
        default_value=366,
        editable_by_admin=True,
        env_key="REPORT_EXPORT_MAX_DATE_RANGE_DAYS",
        min_value=1,
        max_value=3660,
    ),
    "REPORT_EXPORT_CSV_ENCODING": SystemSettingDefinition(
        key="REPORT_EXPORT_CSV_ENCODING",
        display_name="Report Export CSV Encoding",
        description="CSV export encoding policy used for Excel compatibility on Windows.",
        category=SettingCategory.REPORTING,
        data_type=SettingDataType.STRING,
        default_value="utf-8-sig",
        editable_by_admin=False,
        env_key="REPORT_EXPORT_CSV_ENCODING",
    ),
}
