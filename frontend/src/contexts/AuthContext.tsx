import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getMe, login as loginRequest } from "../api/auth";
import { tokenStorageKey } from "../api/client";
import type { CurrentUser } from "../types/api";

type AuthContextValue = {
  user: CurrentUser | null;
  token: string | null;
  loading: boolean;
  login: (
    email: string,
    password: string,
    options?: { requiredRole?: "ADMIN" | "EMPLOYEE"; portalName?: string },
  ) => Promise<CurrentUser>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Loads the saved token into authentication state.
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(tokenStorageKey));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(Boolean(token));

  const logout = useCallback(() => {
    // Clears the saved token and current user state.
    localStorage.removeItem(tokenStorageKey);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    // Listens for expired-session events from the API client.
    const handleExpired = () => logout();
    window.addEventListener("auth:expired", handleExpired);
    return () => window.removeEventListener("auth:expired", handleExpired);
  }, [logout]);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        // Loads the current user for the saved token.
        const currentUser = await getMe();
        if (!cancelled) setUser(currentUser);
      } catch {
        if (!cancelled) logout();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    hydrate();
    return () => {
      cancelled = true;
    };
  }, [logout, token]);

  const login = useCallback(async (email: string, password: string, options?: { requiredRole?: "ADMIN" | "EMPLOYEE"; portalName?: string }) => {
    const response = await loginRequest(email, password);
    // Checks the logged-in user's role for the selected portal.
    if (options?.requiredRole && response.user.role !== options.requiredRole) {
      localStorage.removeItem(tokenStorageKey);
      throw new Error(`This ${options.portalName ?? "portal"} is available to ${options.requiredRole} users only.`);
    }
    localStorage.setItem(tokenStorageKey, response.access_token);
    setToken(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, logout }),
    [user, token, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
