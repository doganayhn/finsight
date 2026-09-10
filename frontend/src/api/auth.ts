import { request, setAccessToken } from "./client";
import type { AuthSession, User } from "../types/contracts";

export async function register(email: string, password: string): Promise<AuthSession> {
  const session = await request<AuthSession>("/auth/register", {
    method: "POST",
    body: { email, password },
    auth: false,
    refreshOnUnauthorized: false,
  });
  setAccessToken(session.access_token);
  return session;
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const session = await request<AuthSession>("/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
    refreshOnUnauthorized: false,
  });
  setAccessToken(session.access_token);
  return session;
}

export const me = (signal?: AbortSignal) => request<User>("/auth/me", { signal });

export async function logout(): Promise<void> {
  try {
    await request<void>("/auth/logout", {
      method: "POST",
      refreshOnUnauthorized: false,
    });
  } finally {
    setAccessToken(null);
  }
}
