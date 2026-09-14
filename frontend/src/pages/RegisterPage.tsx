import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { register } from "../api/auth";
import { useAuth } from "../context/AuthContext";

/** Register page — matches the StudyMate orange/white design language. */
export default function RegisterPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function validate(): string | null {
    if (!fullName.trim()) return "Full name is required.";
    if (!email.trim()) return "Email is required.";
    if (!email.includes("@")) return "Enter a valid email address.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    if (password !== confirmPassword) return "Passwords do not match.";
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setBusy(true);
    try {
      const user = await register({ full_name: fullName.trim(), email: email.trim(), password });
      signIn(user);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || "Registration failed. Please try again.");
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-4">
      <div className="w-full max-w-md">
        {/* Logo / brand */}
        <div className="mb-5 text-center">
          <span className="text-2xl font-bold text-orange-500">Study Companion</span>
          <p className="mt-1 text-sm text-slate-500">Your AI learning partner</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="mb-4 text-xl font-semibold text-slate-800">Create your account</h1>

          {error && (
            <div
              role="alert"
              className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-3">
            <div>
              <label htmlFor="fullName" className="mb-1.5 block text-sm font-medium text-slate-700">
                Full Name
              </label>
              <input
                id="fullName"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={busy}
                placeholder="Jane Smith"
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

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
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                placeholder="Min. 8 characters"
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="mb-1.5 block text-sm font-medium text-slate-700">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={busy}
                placeholder="Repeat your password"
                className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-100 disabled:bg-slate-50"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 w-full rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:opacity-60"
            >
              {busy ? "Creating account…" : "Create Account"}
            </button>
          </form>

          <p className="mt-4 text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-orange-500 hover:text-orange-600">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
