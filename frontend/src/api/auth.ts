import { api } from "./client";

export interface AuthUser {
  access_token: string;
  user_id: string;
  full_name: string;
  email: string;
  role: "learner" | "admin";
}

export function register(body: { full_name: string; email: string; password: string }) {
  return api.post<AuthUser>("/auth/register", body);
}

export function login(body: { email: string; password: string }) {
  return api.post<AuthUser>("/auth/login", body);
}

export function logout() {
  /* stateless JWT: nothing server-side to do */
}
