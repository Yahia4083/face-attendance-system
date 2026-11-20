"""Admin dashboard API routes."""

from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.dashboard_dto import (
    DashboardAttendanceTableRequest,
    DashboardAttendanceTrendRequest,
    DashboardDepartmentSummaryRequest,
    DashboardPendingRequestsRequest,
    DashboardRecentActivityRequest,
    DashboardSummaryRequest,
)
from app.application.use_cases.dashboard.dashboard_management import (
    GetDashboardAttendanceTrend,
    GetDashboardDepartmentSummary,
    GetDashboardPendingRequests,
    GetDashboardRecentActivity,
    GetDashboardSummary,
    GetDashboardTodayAttendance,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.dependencies import (
    get_clock,
    get_dashboard_repository,
    get_department_repository,
    get_employee_repository,
    get_report_repository,
    get_system_settings_provider,
)
from app.domain.repositories.dashboard_repository import DashboardRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.report_repository import ReportRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.dashboard_schema import (
    DashboardAttendanceTableResponse,
    DashboardAttendanceTrendResponse,
    DashboardDepartmentSummaryResponse,
    DashboardPendingRequestsResponse,
    DashboardRecentActivityResponse,
    DashboardSummaryResponse,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _dashboard_kwargs(
    report_repo: ReportRepositoryInterface,
    dashboard_repo: DashboardRepositoryInterface,
    employee_repo: EmployeeRepositoryInterface,
    department_repo: DepartmentRepositoryInterface,
    settings_provider: SystemSettingsProviderInterface,
    clock: ClockInterface,
) -> dict:
    return {
        "report_repo": report_repo,
        "dashboard_repo": dashboard_repo,
        "employee_repo": employee_repo,
        "department_repo": department_repo,
        "settings_provider": settings_provider,
        "clock": clock,
    }


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    on_date: Optional[date] = None,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardSummary(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(DashboardSummaryRequest(on_date=on_date))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/today-attendance", response_model=DashboardAttendanceTableResponse)
def get_dashboard_today_attendance(
    on_date: Optional[date] = None,
    department_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardTodayAttendance(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(
            DashboardAttendanceTableRequest(
                on_date=on_date,
                department_id=department_id,
                employee_id=employee_id,
                status=status,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/pending-requests", response_model=DashboardPendingRequestsResponse)
def get_dashboard_pending_requests(
    request_type: Optional[str] = None,
    employee_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardPendingRequests(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(
            DashboardPendingRequestsRequest(
                request_type=request_type,
                employee_id=employee_id,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/department-summary", response_model=DashboardDepartmentSummaryResponse)
def get_dashboard_department_summary(
    on_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardDepartmentSummary(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(
            DashboardDepartmentSummaryRequest(
                on_date=on_date,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/attendance-trend", response_model=DashboardAttendanceTrendResponse)
def get_dashboard_attendance_trend(
    days: int = 7,
    end_date: Optional[date] = None,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardAttendanceTrend(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(DashboardAttendanceTrendRequest(days=days, end_date=end_date))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)


@router.get("/recent-activity", response_model=DashboardRecentActivityResponse)
def get_dashboard_recent_activity(
    limit: int = 10,
    current_admin=Depends(require_admin),
    report_repo: ReportRepositoryInterface = Depends(get_report_repository),
    dashboard_repo: DashboardRepositoryInterface = Depends(get_dashboard_repository),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = GetDashboardRecentActivity(
        **_dashboard_kwargs(
            report_repo,
            dashboard_repo,
            employee_repo,
            department_repo,
            settings_provider,
            clock,
        )
    )
    try:
        result = use_case.execute(DashboardRecentActivityRequest(limit=limit))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return asdict(result)
