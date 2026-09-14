import { NavLink, Outlet } from "react-router-dom";

const LINKS = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/projects", label: "Spaces & projects" },
  { to: "/admin/activity", label: "Activity" },
  { to: "/admin/learning", label: "Learning analytics" },
  { to: "/admin/ai", label: "AI usage" },
  { to: "/admin/evals", label: "AI evaluation" },
  { to: "/admin/health", label: "System health" },
];

export default function AdminLayout() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Admin dashboard</h1>
        <p className="text-sm text-slate-500">Platform visibility: users, learning activity, AI usage, quality and health.</p>
      </div>
      <nav className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
