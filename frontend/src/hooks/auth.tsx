import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from "../api/auth";
import { refreshSession, setAccessToken, setAuthLostHandler } from "../api/client";
import type { User } from "../types/contracts";

type AuthStatus = "checking" | "authenticated" | "anonymous";
interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [user, setUser] = useState<User | null>(null);
  const queryClient = useQueryClient();

  function clearSession() {
    setAccessToken(null);
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }

  useEffect(() => {
    let active = true;
    setAuthLostHandler(() => {
      if (active) clearSession();
    });
    void refreshSession()
      .then((session) => {
        if (active) {
          setUser(session.user);
          setStatus("authenticated");
        }
      })
      .catch(() => {
        if (active) clearSession();
      });
    return () => {
      active = false;
      setAuthLostHandler(null);
    };
  }, []);

  async function login(email: string, password: string) {
    const session = await loginRequest(email, password);
    queryClient.clear();
    setUser(session.user);
    setStatus("authenticated");
  }

  async function register(email: string, password: string) {
    const session = await registerRequest(email, password);
    queryClient.clear();
    setUser(session.user);
    setStatus("authenticated");
  }

  async function logout() {
    try {
      await logoutRequest();
    } finally {
      clearSession();
    }
  }

  return (
    <AuthContext.Provider value={{ status, user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("Auth context missing");
  return context;
}
