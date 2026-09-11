import { readFileSync } from "node:fs";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App, queryClient } from "../src/App";
import { request, setAccessToken } from "../src/api/client";
import { AccountProvider } from "../src/hooks/context";

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "synthetic@example.com",
  created_at: "2026-09-09T00:00:00Z",
};
const session = { access_token: "memory-access-token", token_type: "bearer", user };
const account = {
  id: "22222222-2222-4222-8222-222222222222",
  display_name: "Sentetik hesap",
  institution_code: null,
  account_type: "CASH",
  currency: "TRY",
  is_active: true,
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
let requests: { url: URL; init: RequestInit }[];
let handler: (url: URL, init: RequestInit) => Response | Promise<Response>;

function installFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      requests.push({ url, init });
      return handler(url, init);
    }),
  );
}

function anonymousHandler(url: URL) {
  if (url.pathname.endsWith("/auth/refresh"))
    return json({ detail: { code: "invalid_refresh_session" } }, 401);
  if (url.pathname.endsWith("/health")) return json({ status: "ok" });
  return json({ detail: { code: "missing_test_handler" } }, 500);
}

function renderApp(path: string) {
  window.history.pushState({}, "", path);
  return render(<App />);
}

function wrapAccount(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><AccountProvider>{node}</AccountProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  requests = [];
  queryClient.clear();
  setAccessToken(null);
  handler = anonymousHandler;
  installFetch();
});

describe("authentication routes and forms", () => {
  it("renders the login route", async () => {
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
  });

  it("renders the registration route", async () => {
    renderApp("/register");
    expect(await screen.findByRole("heading", { name: "FinSight’a başlayın" })).toBeVisible();
  });

  it("redirects an unauthenticated protected route to login", async () => {
    renderApp("/transactions");
    expect(await screen.findByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
    expect(window.location.pathname).toBe("/login");
  });

  it("login sends only the expected credentials", async () => {
    handler = (url, init) => {
      if (url.pathname.endsWith("/auth/refresh")) return anonymousHandler(url);
      if (url.pathname.endsWith("/auth/login")) return json(session);
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      return json({ currencies: [] });
    };
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Şifre"), "correct horse battery staple");
    await userEvent.click(screen.getByRole("button", { name: "Giriş yap" }));
    await screen.findByText(user.email);
    const call = requests.find((entry) => entry.url.pathname.endsWith("/auth/login"));
    expect(JSON.parse(String(call?.init.body))).toEqual({
      email: user.email,
      password: "correct horse battery staple",
    });
  });

  it("registration sends the expected payload without profile data", async () => {
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return anonymousHandler(url);
      if (url.pathname.endsWith("/auth/register")) return json(session, 201);
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [], limit: 50, offset: 0, has_more: false });
      return json({ status: "ok" });
    };
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    const password = "a long synthetic passphrase";
    await userEvent.type(screen.getByLabelText("Şifre", { exact: true }), password);
    await userEvent.type(screen.getByLabelText("Şifreyi doğrula"), password);
    await userEvent.click(screen.getByRole("button", { name: "Hesap oluştur" }));
    await screen.findByRole("heading", { name: "İlk hesabını ekle" });
    const call = requests.find((entry) => entry.url.pathname.endsWith("/auth/register"));
    expect(JSON.parse(String(call?.init.body))).toEqual({ email: user.email, password });
  });

  it("renders invalid credentials as one generic message", async () => {
    handler = (url) =>
      url.pathname.endsWith("/auth/login")
        ? json({ detail: { code: "invalid_credentials" } }, 401)
        : anonymousHandler(url);
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Şifre"), "wrong password value");
    await userEvent.click(screen.getByRole("button", { name: "Giriş yap" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email veya şifre hatalı.");
  });

  it("prevents mismatched password confirmation locally", async () => {
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Şifre", { exact: true }), "correct horse battery");
    await userEvent.type(screen.getByLabelText("Şifreyi doğrula"), "different long password");
    await userEvent.click(screen.getByRole("button", { name: "Hesap oluştur" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Şifreler eşleşmiyor");
    expect(requests.some((entry) => entry.url.pathname.endsWith("/auth/register"))).toBe(false);
  });

  it("declares the 12-character password bound", async () => {
    renderApp("/register");
    const password = await screen.findByLabelText("Şifre", { exact: true });
    expect(password).toHaveAttribute("minlength", "12");
    expect(password).toHaveAttribute("maxlength", "128");
    expect(screen.getByText(/En az 12 karakter/)).toBeVisible();
  });

  it("uses correct browser autocomplete semantics", async () => {
    renderApp("/login");
    expect(await screen.findByLabelText("Email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Şifre")).toHaveAttribute("autocomplete", "current-password");
  });

  it("keeps auth pages usable at a 390px viewport", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    renderApp("/register");
    expect(await screen.findByLabelText("Email")).toBeVisible();
    expect(screen.getByLabelText("Şifreyi doğrula")).toBeVisible();
    expect(screen.getByRole("button", { name: "Hesap oluştur" })).toBeVisible();
  });
});

describe("session restoration and API client", () => {
  it("restores the product session with the refresh cookie", async () => {
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      if (url.pathname.endsWith("/health")) return json({ status: "ok" });
      return json({ currencies: [] });
    };
    renderApp("/not-found");
    expect(await screen.findByText(user.email)).toBeVisible();
    expect(requests[0].url.pathname).toMatch(/\/auth\/refresh$/);
    expect(requests[0].init.credentials).toBe("include");
  });

  it("refresh failure leaves the browser logged out", async () => {
    renderApp("/overview");
    expect(await screen.findByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  });

  it("attaches a Bearer access token and cookie credentials", async () => {
    setAccessToken("memory-only-token");
    handler = () => json({ ok: true });
    await request("/synthetic");
    expect(new Headers(requests[0].init.headers).get("Authorization")).toBe(
      "Bearer memory-only-token",
    );
    expect(requests[0].init.credentials).toBe("include");
  });

  it("refreshes once and retries one unauthorized request once", async () => {
    setAccessToken("expired");
    let protectedCalls = 0;
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      protectedCalls++;
      return protectedCalls === 1 ? json({}, 401) : json({ ok: true });
    };
    await expect(request("/protected")).resolves.toEqual({ ok: true });
    expect(protectedCalls).toBe(2);
    expect(requests.filter((entry) => entry.url.pathname.endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("does not enter an infinite refresh loop", async () => {
    setAccessToken("expired");
    handler = (url) =>
      url.pathname.endsWith("/auth/refresh") ? json(session) : json({}, 401);
    await expect(request("/always-unauthorized")).rejects.toMatchObject({ status: 401 });
    expect(requests.filter((entry) => entry.url.pathname.endsWith("/always-unauthorized"))).toHaveLength(2);
    expect(requests.filter((entry) => entry.url.pathname.endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("shares one in-flight refresh across concurrent 401 responses", async () => {
    setAccessToken("expired");
    let refreshCalls = 0;
    let protectedCalls = 0;
    handler = async (url) => {
      if (url.pathname.endsWith("/auth/refresh")) {
        refreshCalls++;
        await Promise.resolve();
        return json(session);
      }
      protectedCalls++;
      return protectedCalls <= 2 ? json({}, 401) : json({ ok: true });
    };
    await Promise.all([request("/one"), request("/two")]);
    expect(refreshCalls).toBe(1);
  });

  it("does not attach auth to the refresh request itself", async () => {
    setAccessToken("expired-secret");
    handler = (url) => url.pathname.endsWith("/auth/refresh") ? json(session) : json({}, 401);
    await request("/protected").catch(() => undefined);
    const refresh = requests.find((entry) => entry.url.pathname.endsWith("/auth/refresh"));
    expect(new Headers(refresh?.init.headers).has("Authorization")).toBe(false);
  });

  it("never places tokens in URLs", async () => {
    setAccessToken("URL_SENTINEL_TOKEN");
    handler = () => json({ ok: true });
    await request("/safe");
    expect(requests[0].url.href).not.toContain("URL_SENTINEL_TOKEN");
  });
});

describe("account onboarding and logout", () => {
  it("shows zero-account onboarding", async () => {
    setAccessToken("memory-access-token");
    handler = () => json({ accounts: [], limit: 50, offset: 0, has_more: false });
    wrapAccount(<div>product</div>);
    expect(await screen.findByRole("heading", { name: "İlk hesabını ekle" })).toBeVisible();
  });

  it("explains that onboarding does not connect to a bank", async () => {
    setAccessToken("memory-access-token");
    handler = () => json({ accounts: [], limit: 50, offset: 0, has_more: false });
    wrapAccount(<div />);
    expect(await screen.findByText(/bankanıza bağlamaz/)).toBeVisible();
    expect(screen.getByText(/banka kullanıcı adı veya şifresi istemez/)).toBeVisible();
  });

  it("never asks for bank credentials", async () => {
    setAccessToken("memory-access-token");
    handler = () => json({ accounts: [], limit: 50, offset: 0, has_more: false });
    wrapAccount(<div />);
    await screen.findByRole("heading", { name: "İlk hesabını ekle" });
    expect(screen.queryByLabelText(/banka.*şifre/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/kart numarası/i)).not.toBeInTheDocument();
  });

  it("creates an account without a user_id field", async () => {
    setAccessToken("memory-access-token");
    let created = false;
    handler = (url, init) => {
      if (url.pathname.endsWith("/accounts") && init.method === "POST") {
        created = true;
        return json(account, 201);
      }
      return json({ accounts: created ? [account] : [], limit: 50, offset: 0, has_more: false });
    };
    wrapAccount(<div>Ürün hazır</div>);
    await userEvent.click(await screen.findByRole("button", { name: "Hesabı oluştur" }));
    await screen.findByText("Ürün hazır");
    const call = requests.find((entry) => entry.init.method === "POST");
    const body = JSON.parse(String(call?.init.body));
    expect(body).toEqual({
      display_name: "Yapı Kredi TLcard",
      institution_code: "YAPI_KREDI",
      account_type: "DEBIT_CARD",
      currency: "TRY",
    });
    expect(body).not.toHaveProperty("user_id");
  });

  it("makes an existing account selectable", async () => {
    setAccessToken("memory-access-token");
    handler = () => json({ accounts: [account], limit: 50, offset: 0, has_more: false });
    wrapAccount(<div>Ürün hazır</div>);
    expect(await screen.findByRole("option", { name: "Sentetik hesap · TRY" })).toBeVisible();
  });

  it("keeps onboarding controls usable at tablet width", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 768 });
    setAccessToken("memory-access-token");
    handler = () => json({ accounts: [], limit: 50, offset: 0, has_more: false });
    wrapAccount(<div />);
    expect(await screen.findByLabelText("Hesap adı")).toBeVisible();
    expect(screen.getByLabelText("Para birimi")).toBeVisible();
  });

  it("logout calls the backend and returns to login", async () => {
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      if (url.pathname.endsWith("/auth/logout")) return new Response(null, { status: 204 });
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      if (url.pathname.endsWith("/health")) return json({ status: "ok" });
      return json({ currencies: [] });
    };
    renderApp("/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Çıkış yap" }));
    expect(await screen.findByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
    expect(requests.some((entry) => entry.url.pathname.endsWith("/auth/logout"))).toBe(true);
  });

  it("clears local identity when the logout request is unavailable", async () => {
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      if (url.pathname.endsWith("/auth/logout"))
        return json({ detail: { code: "service_unavailable" } }, 503);
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      return json({ status: "ok", currencies: [] });
    };
    renderApp("/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Çıkış yap" }));
    expect(await screen.findByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  });

  it("logout clears TanStack Query financial cache", async () => {
    queryClient.setQueryData(["transactions", "private"], { amount: "999.00" });
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      if (url.pathname.endsWith("/auth/logout")) return new Response(null, { status: 204 });
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      return json({ status: "ok" });
    };
    renderApp("/not-found");
    await userEvent.click(await screen.findByRole("button", { name: "Çıkış yap" }));
    await waitFor(() => expect(queryClient.getQueryData(["transactions", "private"])).toBeUndefined());
  });

  it("displays the authenticated email without exposing a UUID", async () => {
    handler = (url) => {
      if (url.pathname.endsWith("/auth/refresh")) return json(session);
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      return json({ status: "ok", currencies: [] });
    };
    renderApp("/overview");
    expect(await screen.findByText(user.email)).toBeVisible();
    expect(screen.queryByText(user.id)).not.toBeInTheDocument();
  });
});

describe("static token-safety regressions", () => {
  it("contains no development identity product strings", () => {
    const source = readFileSync(`${process.cwd()}/src/hooks/context.tsx`, "utf8");
    expect(source).not.toContain("Geliştirme kullanıcı UUID");
    expect(source).not.toContain("Bağlamı kullan");
  });

  it("contains no development user environment dependency", () => {
    const sources = ["src/api/client.ts", "src/hooks/context.tsx", "src/App.tsx"]
      .map((path) => readFileSync(`${process.cwd()}/${path}`, "utf8"))
      .join("\n");
    expect(sources).not.toContain("VITE_DEV_USER_ID");
    expect(sources).not.toContain("X-Dev-User-ID");
  });

  it("contains no browser token persistence", () => {
    const sources = ["src/api/client.ts", "src/api/auth.ts", "src/hooks/auth.tsx"]
      .map((path) => readFileSync(`${process.cwd()}/${path}`, "utf8"))
      .join("\n");
    expect(sources).not.toMatch(/localStorage.*token/i);
    expect(sources).not.toMatch(/sessionStorage.*token/i);
    expect(sources).not.toContain("indexedDB");
  });

  it("keeps access state in module memory", () => {
    const source = readFileSync(`${process.cwd()}/src/api/client.ts`, "utf8");
    expect(source).toContain("let accessToken: string | null = null");
    expect(source).toContain("credentials: \"include\"");
  });
});
