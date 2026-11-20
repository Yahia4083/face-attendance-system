"""Reporting and export API routes."""

from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.application.dto.report_dto import (
    DailyAttendanceReportRequest,
    DepartmentAttendanceSummaryRequest,
    EmployeeAttendanceSummaryRequest,
    ExportAttendanceReportRequest,
    MonthlyAttendanceReportRequest,
    MyAttendanceSummaryRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.application.use_cases.reports.report_management import (
    ExportAttendanceReport,
    GetDailyAttendanceReport,
    GetDepartmentAttendanceSummary,
    GetEmployeeAttendanceSummary,
    GetMonthlyAttendanceReport,
    GetMyAttendanceSummary,
)
from app.dependencies import (
    get_attendance_export_service,
    get_audit_repository,
    get_department_repository,
    get_employee_repository,
    get_report_repository,
    get_system_settings_provider,
)
from app.domain.enums.export_format import ExportFormat
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.report_repository import (
    AttendanceReportFilters,
    ReportRepositoryInterface,
)
from app.domain.services.attendance_export_service import AttendanceExportServiceInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin, require_employee
from app.presentation.schemas.report_schema import (
    DailyAttendanceReportResponse,
    DepartmentAttendanceSummaryReportResponse,
    EmployeeAttendanceSummaryReportResponse,
    MonthlyAttendanceReportResponse,
)

router = APIRouter(tags=["Reports"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _filters(
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    on_date: Optional[date] = None,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status_value: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
) -> AttendanceReportFilters:
    return AttendanceReportFilters(
        date_from=date_from,
        date_to=date_to,
        on_date=on_date,
        employee_id=employee_id,
        department_id=department_id,
        status=status_value,
        is_late=is_late,
        is_early_departure=is_early_departure,
        is_unscheduled=is_unscheduled,
        is_missing_checkout=is_missing_checkout,
        justification_status=justification_status,
        overtime_status=overtime_status,
    )


def _report_base_kwargs(
    report_repo: ReportRepositoryInterface,
    employee_repo: EmployeeRepositoryInterface,
    department_repo: DepartmentRepositoryInterface,
) -> dict:
    return {
        "report_repo": report_repo,
        "employee_repo": employee_repo,
        "department_repo": department_repo,
    }


@router.get("/reports/attendance/daily", response_model=DailyAttendanceReportResponse)
def get_daily_attendance_report(
    on_date: date,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    use_case = GetDailyAttendanceReport(
        **_report_base_kwargs(report_repo, employee_repo, department_repo)
    )
    try:
        result = use_case.execute(
            DailyAttendanceReportRequest(
                on_date=on_date,
                filters=_filters(
                    on_date=on_date,
                    employee_id=employee_id,
                    department_id=department_id,
                    status_value=status,
                    is_late=is_late,
                    is_early_departure=is_early_departure,
                    is_unscheduled=is_unscheduled,
                    is_missing_checkout=is_missing_checkout,
                    justification_status=justification_status,
                    overtime_status=overtime_status,
                ),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/reports/attendance/monthly", response_model=MonthlyAttendanceReportResponse)
def get_monthly_attendance_report(
    year: int,
    month: int,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    use_case = GetMonthlyAttendanceReport(
        **_report_base_kwargs(report_repo, employee_repo, department_repo)
    )
    try:
        result = use_case.execute(
            MonthlyAttendanceReportRequest(
                year=year,
                month=month,
                filters=_filters(employee_id=employee_id, department_id=department_id),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get(
    "/reports/employees/{employee_id}/summary",
    response_model=EmployeeAttendanceSummaryReportResponse,
)
def get_employee_attendance_summary(
    employee_id: int,
    date_from: date,
    date_to: date,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    use_case = GetEmployeeAttendanceSummary(
        **_report_base_kwargs(report_repo, employee_repo, department_repo)
    )
    try:
        result = use_case.execute(
            EmployeeAttendanceSummaryRequest(
                employee_id=employee_id,
                date_from=date_from,
                date_to=date_to,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get(
    "/reports/departments/{department_id}/summary",
    response_model=DepartmentAttendanceSummaryReportResponse,
)
def get_department_attendance_summary(
    department_id: int,
    date_from: date,
    date_to: date,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    use_case = GetDepartmentAttendanceSummary(
        **_report_base_kwargs(report_repo, employee_repo, department_repo)
    )
    try:
        result = use_case.execute(
            DepartmentAttendanceSummaryRequest(
                department_id=department_id,
                date_from=date_from,
                date_to=date_to,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/reports/attendance/export")
def export_attendance_report(
    request: Request,
    date_from: date,
    date_to: date,
    export_format: ExportFormat = Query(..., alias="format"),
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    export_service: AttendanceExportServiceInterface = Depends(get_attendance_export_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = ExportAttendanceReport(
        report_repo=report_repo,
        employee_repo=employee_repo,
        department_repo=department_repo,
        export_service=export_service,
        audit_repo=audit_repo,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            ExportAttendanceReportRequest(
                filters=_filters(
                    date_from=date_from,
                    date_to=date_to,
                    employee_id=employee_id,
                    department_id=department_id,
                    status_value=status,
                    is_late=is_late,
                    is_early_departure=is_early_departure,
                    is_unscheduled=is_unscheduled,
                    is_missing_checkout=is_missing_checkout,
                    justification_status=justification_status,
                    overtime_status=overtime_status,
                ),
                export_format=export_format,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get(
    "/me/reports/attendance-summary",
    response_model=EmployeeAttendanceSummaryReportResponse,
)
def get_my_attendance_summary(
    date_from: date,
    date_to: date,
    current_employee=Depends(require_employee),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    use_case = GetMyAttendanceSummary(
        **_report_base_kwargs(report_repo, employee_repo, department_repo)
    )
    try:
        result = use_case.execute(
            MyAttendanceSummaryRequest(
                user_id=current_employee.id,
                date_from=date_from,
                date_to=date_to,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/me/reports/attendance/export")
def export_my_attendance_report(
    request: Request,
    date_from: date,
    date_to: date,
    export_format: ExportFormat = Query(..., alias="format"),
    current_employee=Depends(require_employee),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    export_service: AttendanceExportServiceInterface = Depends(get_attendance_export_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = ExportAttendanceReport(
        report_repo=report_repo,
        employee_repo=employee_repo,
        department_repo=department_repo,
        export_service=export_service,
        audit_repo=audit_repo,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            ExportAttendanceReportRequest(
                filters=_filters(date_from=date_from, date_to=date_to),
                export_format=export_format,
                actor_user_id=current_employee.id,
                own_user_id=current_employee.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
