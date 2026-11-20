import { BarChart3, Building2, CalendarDays, ClipboardList, Gauge, History, Settings, UserRoundCog, Users } from "lucide-react";
import { PortalLayout, type PortalNavItem } from "./PortalLayout";

const navItems: PortalNavItem[] = [
  { to: "/", label: "Dashboard", icon: Gauge, group: "Overview" },
  { to: "/employees", label: "Employees", icon: Users, group: "Workforce" },
  { to: "/departments", label: "Departments", icon: Building2, group: "Workforce" },
  { to: "/schedules", label: "Schedules", icon: CalendarDays, group: "Workforce" },
  { to: "/attendance", label: "Attendance Management", icon: ClipboardList, group: "Attendance" },
  { to: "/requests", label: "Requests", icon: UserRoundCog, group: "Attendance" },
  { to: "/reports", label: "Reports", icon: BarChart3, group: "Analysis" },
  { to: "/settings", label: "System Settings", icon: Settings, group: "Administration" },
  { to: "/audit-logs", label: "Audit Logs", icon: History, group: "Administration" },
];

export function AdminLayout() {
  return (
    <PortalLayout
      portalLabel="Admin Portal"
      headerEyebrow="Administrative workspace"
      brandTitle="Face Recognition Attendance"
      navItems={navItems}
      footerText="Administrative interface only. Attendance remains camera-based through the recognition workflow."
      sidebarWidth="256px"
    />
  );
}
