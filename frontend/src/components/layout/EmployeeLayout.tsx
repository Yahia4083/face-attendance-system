import { CalendarClock, ClipboardList, FileBarChart, FileText, Gauge, UserRound } from "lucide-react";
import { PortalLayout, type PortalNavItem } from "./PortalLayout";

const navItems: PortalNavItem[] = [
  { to: "/employee", label: "Dashboard", icon: Gauge },
  { to: "/employee/attendance", label: "My Attendance", icon: ClipboardList },
  { to: "/employee/schedule", label: "My Schedule", icon: CalendarClock },
  { to: "/employee/requests", label: "My Requests", icon: FileText },
  { to: "/employee/reports", label: "My Reports", icon: FileBarChart },
  { to: "/employee/profile", label: "Profile", icon: UserRound },
];

export function EmployeeLayout() {
  return (
    <PortalLayout
      portalLabel="Employee Portal"
      headerEyebrow="Employee self-service"
      brandTitle="My Attendance Workspace"
      navItems={navItems}
      footerText="Self-service only. Check-in and check-out are recorded by the camera-based recognition workflow."
      sidebarWidth="248px"
    />
  );
}
