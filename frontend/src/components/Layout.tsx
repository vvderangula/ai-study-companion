import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { user, isAdmin, signOut } = useAuth();
  const navigate = useNavigate();
  const links = [
    { to: "/", label: "Home", end: true },
    { to: "/spaces", label: "Spaces", end: false },
    { to: "/analytics", label: "Analytics", end: false },
    { to: "/context", label: "About me", end: false },
    ...(isAdmin ? [{ to: "/admin", label: "Admin", end: false }] : []),
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-y-2 px-4 py-3 sm:flex-nowrap sm:px-6">
          <Link to="/" className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-orange-500 text-white">S</span>
            Study Companion
          </Link>
          <nav className="order-last flex w-full items-center gap-1 sm:order-none sm:w-auto">
            {links.map(({ to, label, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `rounded-lg px-3 py-1.5 text-sm font-medium transition ${isActive ? "bg-orange-50 text-orange-600" : "text-slate-600 hover:bg-slate-100"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:inline">{user?.full_name}</span>
            <button
              type="button"
              onClick={() => {
                signOut();
                navigate("/login", { replace: true });
              }}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
