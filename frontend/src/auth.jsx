import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { api } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // undefined — ещё не знаем, null — не вошёл.
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    api("GET", "/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  const login = useCallback(async (email, password) => {
    setUser(await api("POST", "/api/auth/login", { email, password }));
  }, []);

  const register = useCallback(async (email, password, name) => {
    setUser(await api("POST", "/api/auth/register", { email, password, name }));
  }, []);

  const logout = useCallback(async () => {
    await api("POST", "/api/auth/logout");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

// Страницы только для вошедших: остальных отправляем на вход и возвращаем обратно.
export function RequireAuth({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <p className="muted">Загрузка…</p>;
  if (user === null) {
    const next = encodeURIComponent(location.pathname);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}
