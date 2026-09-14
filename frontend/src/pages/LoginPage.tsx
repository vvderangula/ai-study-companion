import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { login } from "../api/auth";
import { useAuth } from "../context/AuthContext";

// Demo accounts for evaluators (PRD 83). Set VITE_SHOW_DEMO_LOGINS=false to hide
// them on a deployment that carries real user data.
const SHOW_DEMO = import.meta.env.VITE_SHOW_DEMO_LOGINS !== "false";
const DEMO_ACCOUNTS = [
  { label: "Student", email: "demo@example.com", password: "demo12345" },
  { label: "Admin", email: "admin@example.com", password: "admin12345" },
];

/** Login page — matches the StudyMate orange/white design language. */
export default function LoginPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    if (!password) {
      setError("Password is required.");
      return;
    }

    await signInWith(email.trim(), password);
  }

  async function signInWith(emailValue: string, passwordValue: string) {
    setError("");
    setBusy(true);
    try {
      const user = await login({ email: emailValue, password: passwordValue });
      signIn(user);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || "Invalid email or password.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        {/* Logo / brand */}
        <div className="mb-8 text-center">
          <span className="text-3xl font-bold text-orange-500">Study Companion</span>
          <p className="mt-1 text-sm text-slate-500">Your AI learning partner</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="mb-6 text-xl font-semibold text-slate-800">Welcome back</h1>

          {error && (
            <div
              role="alert"
              className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 w-full rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign In"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-slate-500">
            Don&apos;t have an account?{" "}
            <Link to="/register" className="font-medium text-orange-500 hover:text-orange-600">
              Create one
            </Link>
          </p>

          {SHOW_DEMO && (
            <div className="mt-6 border-t border-slate-200 pt-5">
              <p className="text-center text-xs font-medium uppercase tracking-wide text-slate-400">
                Just looking around?
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {DEMO_ACCOUNTS.map((a) => (
                  <button
                    key={a.email}
                    type="button"
                    disabled={busy}
                    onClick={() => void signInWith(a.email, a.password)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-orange-300 hover:bg-orange-50 disabled:opacity-60"
                  >
                    Sign in as {a.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-center text-xs text-slate-400">
                {DEMO_ACCOUNTS.map((a) => `${a.email} / ${a.password}`).join(" · ")}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
