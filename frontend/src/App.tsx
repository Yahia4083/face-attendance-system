import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AdminLayout } from "./components/layout/AdminLayout";
import { EmployeeLayout } from "./components/layout/EmployeeLayout";
import { LoadingState } from "./components/common/State";
import { useAuth } from "./contexts/AuthContext";

const AttendanceManagementPage = lazy(() => import("./pages/AttendanceManagementPage").then((module) => ({ default: module.AttendanceManagementPage })));
const AuditLogsPage = lazy(() => import("./pages/AuditLogsPage").then((module) => ({ default: module.AuditLogsPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const DepartmentsPage = lazy(() => import("./pages/DepartmentsPage").then((module) => ({ default: module.DepartmentsPage })));
const EmployeesPage = lazy(() => import("./pages/EmployeesPage").then((module) => ({ default: module.EmployeesPage })));
const EmployeeDashboardPage = lazy(() => import("./pages/employee/EmployeeDashboardPage").then((module) => ({ default: module.EmployeeDashboardPage })));
const EmployeeLoginPage = lazy(() => import("./pages/employee/EmployeeLoginPage").then((module) => ({ default: module.EmployeeLoginPage })));
const EmployeeProfilePage = lazy(() => import("./pages/employee/EmployeeProfilePage").then((module) => ({ default: module.EmployeeProfilePage })));
const ForcedPasswordChangePage = lazy(() => import("./pages/employee/ForcedPasswordChangePage").then((module) => ({ default: module.ForcedPasswordChangePage })));
const MyAttendancePage = lazy(() => import("./pages/employee/MyAttendancePage").then((module) => ({ default: module.MyAttendancePage })));
const MyReportsPage = lazy(() => import("./pages/employee/MyReportsPage").then((module) => ({ default: module.MyReportsPage })));
const MyRequestsPage = lazy(() => import("./pages/employee/MyRequestsPage").then((module) => ({ default: module.MyRequestsPage })));
const MySchedulePage = lazy(() => import("./pages/employee/MySchedulePage").then((module) => ({ default: module.MySchedulePage })));
const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage })));
const RequestsPage = lazy(() => import("./pages/RequestsPage").then((module) => ({ default: module.RequestsPage })));
const SchedulesPage = lazy(() => import("./pages/SchedulesPage").then((module) => ({ default: module.SchedulesPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));

function FullScreenLoading({ label }: { label: string }) {
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <LoadingState label={label} />
      </div>
    </div>
  );
}

function ProtectedAdminRoute() {
  const { user, token, loading, logout } = useAuth();
  const location = useLocation();

  // Displays the admin loading state while authentication is being checked.
  if (loading) {
    return <FullScreenLoading label="Loading secure admin portal..." />;
  }

  if (!token || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // Redirects non-admin users away from admin routes.
  if (user.role !== "ADMIN") {
    logout();
    return <Navigate to="/login" replace state={{ unauthorized: true }} />;
  }

  return <AdminLayout />;
}

function ProtectedEmployeeRoute() {
  const { user, token, loading, logout } = useAuth();
  const location = useLocation();

  // Displays the employee loading state while authentication is being checked.
  if (loading) {
    return <FullScreenLoading label="Loading secure employee portal..." />;
  }

  if (!token || !user) {
    return <Navigate to="/employee/login" replace state={{ from: location }} />;
  }

  // Redirects non-employee users away from employee routes.
  if (user.role !== "EMPLOYEE") {
    logout();
    return <Navigate to="/employee/login" replace state={{ unauthorized: true }} />;
  }
  if (user.must_change_password) {
    return <Navigate to="/employee/change-password" replace />;
  }

  return <EmployeeLayout />;
}

function ProtectedEmployeePasswordRoute() {
  const { user, token, loading, logout } = useAuth();
  const location = useLocation();

  if (loading) {
    return <FullScreenLoading label="Loading account security..." />;
  }
  if (!token || !user) {
    return <Navigate to="/employee/login" replace state={{ from: location }} />;
  }
  if (user.role !== "EMPLOYEE") {
    logout();
    return <Navigate to="/employee/login" replace state={{ unauthorized: true }} />;
  }
  return <ForcedPasswordChangePage />;
}

export function App() {
  return (
    <Suspense fallback={<FullScreenLoading label="Loading page..." />}>
    <Routes>
      {/* Registers public login routes for both portals. */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/employee/login" element={<EmployeeLoginPage />} />
      <Route path="/employee/change-password" element={<ProtectedEmployeePasswordRoute />} />
      {/* Registers protected administrative management routes. */}
      <Route element={<ProtectedAdminRoute />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/attendance" element={<AttendanceManagementPage />} />
        <Route path="/employees" element={<EmployeesPage />} />
        <Route path="/departments" element={<DepartmentsPage />} />
        <Route path="/schedules" element={<SchedulesPage />} />
        <Route path="/requests" element={<RequestsPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/audit-logs" element={<AuditLogsPage />} />
      </Route>
      {/* Registers protected employee self-service routes. */}
      <Route element={<ProtectedEmployeeRoute />}>
        <Route path="/employee" element={<EmployeeDashboardPage />} />
        <Route path="/employee/attendance" element={<MyAttendancePage />} />
        <Route path="/employee/schedule" element={<MySchedulePage />} />
        <Route path="/employee/requests" element={<MyRequestsPage />} />
        <Route path="/employee/reports" element={<MyReportsPage />} />
        <Route path="/employee/profile" element={<EmployeeProfilePage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    </Suspense>
  );
}
