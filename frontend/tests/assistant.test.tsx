import { readFileSync } from "node:fs";
import { useState } from "react";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ProductShell } from "../src/App";
import { Assistant } from "../src/pages/Assistant";
import { AccountProvider } from "../src/hooks/context";
import { AuthProvider } from "../src/hooks/auth";
import { setAccessToken } from "../src/api/client";

const userId = "11111111-1111-4111-8111-111111111111";
const accountId = "22222222-2222-4222-8222-222222222222";
const account = {
  id: accountId,
  display_name: "Sentetik hesap",
  institution_code: null,
  account_type: "CASH",
  currency: "TRY",
  is_active: true,
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
let handler: ((url: URL, init: RequestInit) => Response | Promise<Response> | undefined) | undefined;
let requests: { url: URL; init: RequestInit }[];

beforeEach(() => {
  setAccessToken("synthetic-access-token");
  handler = undefined;
  requests = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      requests.push({ url, init });
      const override = handler?.(url, init);
      if (override) return override;
      if (url.pathname.endsWith("/auth/refresh"))
        return json({
          access_token: "synthetic-access-token",
          token_type: "bearer",
          user: { id: userId, email: "synthetic@example.com", created_at: "2026-01-01T00:00:00Z" },
        });
      if (url.pathname.endsWith("/health")) return json({ status: "ok" });
      if (url.pathname.endsWith("/accounts"))
        return json({ accounts: [account], limit: 50, offset: 0, has_more: false });
      if (url.pathname.endsWith("/assistant/status"))
        return json({ enabled: true, provider: "Groq", model: "synthetic-model" });
      if (url.pathname.endsWith("/assistant/chat"))
        return json({
          answer: "TRY 120.00",
          used_tools: [{ name: "get_spending_summary", label: "Harcama özeti" }],
          scope: { account_id: null, data_scope: "CANONICAL_TRANSACTIONS" },
        });
      return json({ detail: { code: "missing_test_handler" } }, 500);
    }),
  );
});

function wrap(node: ReactNode, route = "/assistant") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}>
        <AccountProvider>{node}</AccountProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const waitUntilReady = () =>
  screen.findByRole("button", { name: "Bu ay ne kadar harcadım?" });

it("adds the Assistant navigation item and renders the route", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/assistant"]}><AuthProvider><ProductShell /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByRole("link", { name: /Asistan/ })).toHaveAttribute("href", "/assistant");
  expect(await screen.findByRole("heading", { name: "Harcamalarınızı sorun." })).toBeVisible();
});

it("shows privacy, provider, raw-PDF, memory, and data-coverage disclosures", async () => {
  wrap(<Assistant />);
  expect(await screen.findByText(/Asistana yazdığınız mesaj.*Groq/)).toBeVisible();
  expect(screen.getByText(/türetilmiş finansal veriler.*Groq/)).toBeVisible();
  expect(screen.getByText(/Ham hesap özeti PDF’leri/)).toBeVisible();
  expect(screen.getByText(/çıkarılmış PDF metni/)).toBeVisible();
  expect(screen.getByText(/güncel banka bakiyesini göstermez/)).toBeVisible();
  expect(screen.getByText(/sekmenin belleğinde tutulur/)).toBeVisible();
});

it("shows all-accounts and selected-account scope from product context", async () => {
  wrap(<Assistant />);
  await waitUntilReady();
  expect(within(screen.getByLabelText("Asistan hesap kapsamı")).getByText("Tüm hesaplar")).toBeVisible();
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Hesap" }), accountId);
  expect(await screen.findByText("Sentetik hesap")).toBeVisible();
});

it("starter question sends a bounded request with backend request scope", async () => {
  wrap(<Assistant />);
  await userEvent.click(await screen.findByRole("button", { name: "Bu ay ne kadar harcadım?" }));
  await screen.findByText("TRY 120.00");
  const sent = requests.find((entry) => entry.url.pathname.endsWith("/assistant/chat"));
  const body = JSON.parse(String(sent?.init.body));
  expect(body.message).toBe("Bu ay ne kadar harcadım?");
  expect(body.history).toEqual([]);
  expect(body.account_id).toBeNull();
  expect(body.client_timezone).toBeTruthy();
  expect(new Headers(sent?.init.headers).get("Authorization")).toBe("Bearer synthetic-access-token");
  expect(new Headers(sent?.init.headers).has("X-Dev-User-ID")).toBe(false);
});

it("submits typed text and renders safe plain text with tool metadata", async () => {
  handler = (url) =>
    url.pathname.endsWith("/assistant/chat")
      ? json({
          answer: '<img src=x onerror="alert(1)"> TRY 120.00',
          used_tools: [{ name: "get_spending_summary", label: "Harcama özeti" }],
          scope: { account_id: null, data_scope: "CANONICAL_TRANSACTIONS" },
        })
      : undefined;
  const view = wrap(<Assistant />);
  await waitUntilReady();
  await userEvent.type(await screen.findByLabelText("Sorunuz"), "Bu ay?");
  await userEvent.click(screen.getByRole("button", { name: "Gönder" }));
  expect(await screen.findByText(/<img src=x/)).toBeVisible();
  expect(view.container.querySelector("img")).toBeNull();
  expect(screen.getByText("Harcama özeti")).toBeVisible();
});

it("pending state blocks a second submission", async () => {
  let resolve!: (response: Response) => void;
  handler = (url) =>
    url.pathname.endsWith("/assistant/chat")
      ? new Promise<Response>((done) => { resolve = done; })
      : undefined;
  wrap(<Assistant />);
  await waitUntilReady();
  const input = await screen.findByLabelText("Sorunuz");
  await userEvent.type(input, "Bekleyen soru");
  fireEvent.submit(input.closest("form")!);
  expect(await screen.findByText("FinSight verilerinizi inceliyor…")).toBeVisible();
  fireEvent.submit(input.closest("form")!);
  expect(requests.filter((entry) => entry.url.pathname.endsWith("/assistant/chat"))).toHaveLength(1);
  resolve(json({ answer: "Bitti", used_tools: [], scope: { account_id: null, data_scope: "CANONICAL_TRANSACTIONS" } }));
  expect(await screen.findByText("Bitti")).toBeVisible();
});

it("shows a calm provider-unavailable state without breaking the page", async () => {
  handler = (url) =>
    url.pathname.endsWith("/assistant/status")
      ? json({ enabled: false, provider: "Groq", model: "synthetic" })
      : undefined;
  wrap(<Assistant />);
  expect(await screen.findByText(/Asistan bu yerel ortamda etkin değil/)).toBeVisible();
  expect(screen.getByLabelText("Sorunuz")).toBeDisabled();
});

it("maps provider rate limit to a safe Turkish error", async () => {
  handler = (url) =>
    url.pathname.endsWith("/assistant/chat")
      ? json({ detail: { code: "assistant_rate_limited" } }, 429)
      : undefined;
  wrap(<Assistant />);
  await waitUntilReady();
  await userEvent.type(await screen.findByLabelText("Sorunuz"), "Soru");
  await userEvent.click(screen.getByRole("button", { name: "Gönder" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Asistan şu anda yoğun");
});

it("sends only recent in-memory user/assistant conversation history", async () => {
  wrap(<Assistant />);
  await waitUntilReady();
  const input = await screen.findByLabelText("Sorunuz");
  await userEvent.type(input, "Birinci");
  await userEvent.click(screen.getByRole("button", { name: "Gönder" }));
  await screen.findByText("TRY 120.00");
  await userEvent.type(input, "İkinci");
  await userEvent.click(screen.getByRole("button", { name: "Gönder" }));
  await waitFor(() => expect(requests.filter((entry) => entry.url.pathname.endsWith("/assistant/chat"))).toHaveLength(2));
  const chats = requests.filter((entry) => entry.url.pathname.endsWith("/assistant/chat"));
  const history = JSON.parse(String(chats[1].init.body)).history;
  expect(history).toEqual([
    { role: "user", content: "Birinci" },
    { role: "assistant", content: "TRY 120.00" },
  ]);
});

it("changing account scope clears the conversation and cancels its context", async () => {
  wrap(<Assistant />);
  await userEvent.click(await screen.findByRole("button", { name: "Bu ay ne kadar harcadım?" }));
  expect(await screen.findByText("TRY 120.00")).toBeVisible();
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Hesap" }), accountId);
  await waitFor(() => expect(screen.queryByText("TRY 120.00")).not.toBeInTheDocument());
});

it("has no development identity UI or browser persistence", async () => {
  wrap(<Assistant />);
  await waitUntilReady();
  expect(screen.queryByText("Bağlamı değiştir")).not.toBeInTheDocument();
  expect(sessionStorage.length).toBe(0);
});

it("does not combine a multi-currency provider answer in the browser", async () => {
  handler = (url) =>
    url.pathname.endsWith("/assistant/chat")
      ? json({ answer: "TRY 125.40\nUSD 10.00", used_tools: [], scope: { account_id: null, data_scope: "CANONICAL_TRANSACTIONS" } })
      : undefined;
  wrap(<Assistant />);
  await userEvent.click(await screen.findByRole("button", { name: "Bu ay ne kadar harcadım?" }));
  expect(await screen.findByText(/TRY 125.40/)).toHaveTextContent("TRY 125.40 USD 10.00");
  expect(screen.queryByText("135.40")).not.toBeInTheDocument();
});

it("keeps the mobile page controls accessible", async () => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
  wrap(<Assistant />);
  expect(await screen.findByLabelText("Sorunuz")).toBeVisible();
  expect(screen.getByRole("button", { name: "Gönder" })).toBeVisible();
  expect(screen.getByLabelText("Asistan hesap kapsamı")).toBeVisible();
});

it("source has no dangerous HTML or browser conversation persistence", () => {
  const source = readFileSync(`${process.cwd()}/src/pages/Assistant.tsx`, "utf8");
  expect(source).not.toContain("dangerouslySetInnerHTML");
  expect(source).not.toContain("localStorage");
  expect(source).not.toContain("indexedDB");
});
