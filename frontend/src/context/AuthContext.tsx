import { createContext, useContext, useState, type ReactNode } from "react";
import { getToken, removeToken, setToken } from "../api/client";
import type { AuthUser } from "../api/auth";

export interface StoredUser {
  user_id: string;
  full_name: string;
  email: string;
  role: "learner" | "admin";
}

interface AuthContextValue {
  user: StoredUser | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  signIn: (user: AuthUser) => void;
  signOut: () => void;
}

const USER_KEY = "studymate_user";

function loadStoredUser(): StoredUser | null {
  try {
    if (!getToken()) return null;
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    return null;
  }
}

const AuthContext = createContext<AuthContextValue>({ user: null, isAuthenticated: false, isAdmin: false, signIn: () => {}, signOut: () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<StoredUser | null>(loadStoredUser);

  function signIn(authUser: AuthUser) {
    const stored: StoredUser = { user_id: authUser.user_id, full_name: authUser.full_name, email: authUser.email, role: authUser.role };
    setToken(authUser.access_token);
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(stored));
    } catch {
      /* ignore */
    }
    setUser(stored);
  }

  function signOut() {
    removeToken();
    try {
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, isAuthenticated: user !== null, isAdmin: user?.role === "admin", signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
