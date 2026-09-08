import { useState } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DevelopmentProvider } from "../src/hooks/context";
import { Overview } from "../src/pages/Overview";
import { Transactions, CorrectionDialog } from "../src/pages/Transactions";
import { Imports, ImportDetail, PreviewContent } from "../src/pages/Imports";
import { ProductShell } from "../src/App";
import { ApiError, errorMessage } from "../src/api/client";
import {
  decimal,
  money,
  monthPeriod,
  precedingPeriod,
} from "../src/utils/presentation";
import type {
  ImportPreview,
  Decisions,
  Transaction,
} from "../src/types/contracts";
import type { ReactNode } from "react";

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
const category = { id: "cafe", code: "CAFE", display_name: "Cafe" };
const metrics = {
  gross_spending: "1234.56",
  refunds: "34.56",
  net_spending: "1200.00",
  financial_fees: "25.00",
  cash_withdrawals: "500.00",
  expense_transaction_count: 2,
  refund_transaction_count: 1,
};
const row: Transaction = {
  id: "transaction",
  account_id: accountId,
  transaction_date: "2026-08-15",
  posted_date: null,
  description_raw: "SYNTHETIC ORIGINAL",
  merchant_normalized: "Demo Store",
  amount: "-1234.56",
  currency: "TRY",
  transaction_type: "EXPENSE",
  category,
  category_source: "UNKNOWN",
  review_status: "NEEDS_REVIEW",
  installment_index: null,
  installment_count: null,
  installment_plan_id: null,
};
const preview: ImportPreview = {
  import_batch_id: "batch",
  status: "AWAITING_CONFIRMATION",
  institution_code: "YAPI_KREDI",
  statement_type: "TLCARD",
  currency: "TRY",
  statement_period: "2026-08",
  parser: { name: "unused", version: "1" },
  reported_total: "100.00",
  parsed_total: "100.00",
  validation_status: "PASSED",
  counts: {
    total_rows: 1,
    valid_rows: 1,
    failed_rows: 0,
    duplicate_rows: 0,
    imported_rows: 0,
    skipped_duplicate_rows: 0,
  },
  transactions: [
    {
      id: "candidate",
      transaction_date: "2026-08-15",
      posted_date: null,
      description_raw: "SYNTHETIC PURCHASE",
      merchant_raw: "Demo market",
      amount: "-100.00",
      currency: "TRY",
      transaction_type: "EXPENSE",
      source_transaction_id: null,
      source_row_number: 1,
      source_page_number: 1,
      duplicate_matches: [],
    },
  ],
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
let requests: { url: URL; init: RequestInit }[];
let handler:
  | ((url: URL, init: RequestInit) => Response | Promise<Response> | undefined)
  | undefined;
beforeEach(() => {
  requests = [];
  handler = undefined;
  sessionStorage.setItem("finsight.devUserId", userId);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit) => {
      const url = new URL(input);
      requests.push({ url, init });
      const override = handler?.(url, init);
      if (override) return override;
      if (url.pathname.endsWith("/health")) return json({ status: "ok" });
      if (url.pathname.endsWith("/accounts"))
        return json({
          accounts: [account],
          limit: 50,
          offset: 0,
          has_more: false,
        });
      if (url.pathname === "/api/v1/categories")
        return json([
          category,
          { id: "shopping", code: "SHOPPING", display_name: "Shopping" },
        ]);
      if (url.pathname.endsWith("/summary"))
        return json({
          currencies: [
            { currency: "TRY", ...metrics },
            { currency: "USD", ...metrics, net_spending: "50.01" },
          ],
        });
      if (url.pathname.endsWith("/analytics/categories"))
        return json({
          currencies: [
            {
              currency: "TRY",
              categories: [
                {
                  category_id: "cafe",
                  category_code: "CAFE",
                  category_name: "Cafe",
                  ...metrics,
                  transaction_count: 2,
                },
              ],
            },
          ],
        });
      if (url.pathname.endsWith("/merchants"))
        return json({
          currencies: [
            {
              currency: "TRY",
              merchants: [
                {
                  merchant: "Demo Store",
                  identity_source: "NORMALIZED",
                  ...metrics,
                  transaction_count: 2,
                },
              ],
            },
          ],
        });
      if (url.pathname.endsWith("/trend"))
        return json({
          currencies: [
            { currency: "TRY", months: [{ month: "2026-08", ...metrics }] },
          ],
        });
      if (url.pathname.endsWith("/compare"))
        return json({
          currencies: [
            {
              currency: "TRY",
              current_net_spending: "1200.00",
              previous_net_spending: "0.00",
              absolute_change: "1200.00",
              percentage_change: null,
              percentage_state: "PREVIOUS_ZERO",
              direction: "INCREASE",
            },
          ],
        });
      if (url.pathname.endsWith("/projection"))
        return json({
          elapsed_days: 15,
          days_in_month: 31,
          currencies: [
            {
              currency: "TRY",
              observed_net_spending: "1200.00",
              average_daily_spending: "80.00",
              projected_month_spending: "2480.00",
            },
          ],
        });
      if (url.pathname.endsWith("/classification"))
        return json({
          ...row,
          category_source: "USER",
          review_status: "USER_CONFIRMED",
        });
      if (url.pathname.endsWith("/transactions"))
        return json({
          transactions: [row],
          has_more: url.searchParams.get("offset") === "0",
          limit: 20,
          offset: Number(url.searchParams.get("offset")),
        });
      if (url.pathname.endsWith("/imports"))
        return json({ imports: [], limit: 20, offset: 0, has_more: false });
      if (url.pathname.endsWith("/confirm"))
        return json({
          ...preview,
          status: "COMPLETED",
          transactions: [],
          counts: { ...preview.counts, imported_rows: 1 },
        });
      return json(preview);
    }),
  );
});
function wrap(
  node: ReactNode,
  route = "/overview",
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <DevelopmentProvider>{node}</DevelopmentProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}
function PreviewHarness({
  data = preview,
  pending = false,
}: {
  data?: ImportPreview;
  pending?: boolean;
}) {
  const [decisions, setDecisions] = useState<Decisions>({});
  return (
    <MemoryRouter>
      <PreviewContent
        data={data}
        decisions={decisions}
        onDecision={(id, v) => setDecisions({ ...decisions, [id]: v })}
        onConfirm={() => {}}
        pending={pending}
      />
    </MemoryRouter>
  );
}
describe("presentation and API errors", () => {
  it("keeps large decimal cents and currencies exact", () => {
    expect(decimal("19999999999999999.98")).toBe("19.999.999.999.999.999,98");
    expect(money("-12.30", "USD")).toBe("-12,30 USD");
    expect(money(null, "TRY")).toBe("—");
  });
  it("uses deterministic calendar boundaries", () => {
    expect(monthPeriod(new Date(2024, 2, 12), -1)).toEqual({
      start_date: "2024-02-01",
      end_date: "2024-02-29",
    });
    expect(precedingPeriod("2024-03-01", "2024-03-31")).toEqual({
      start_date: "2024-01-30",
      end_date: "2024-02-29",
    });
  });
  it.each([403, 404, 409, 413, 415, 422, 500])(
    "translates HTTP %i without raw details",
    (status) => {
      expect(
        errorMessage(new ApiError(status, "PRIVATE_SENTINEL")),
      ).not.toContain("PRIVATE_SENTINEL");
      expect(errorMessage(new ApiError(status, "unknown"))).not.toBe("");
    },
  );
});
describe("overview", () => {
  it("applies explicit custom dates to backend queries only after form submission", async () => {
    wrap(<Overview />);
    await screen.findByRole("region", { name: "TRY harcama özeti" });
    fireEvent.change(screen.getByLabelText("Başlangıç", { exact: true }), {
      target: { value: "2024-02-01" },
    });
    fireEvent.change(screen.getByLabelText("Bitiş", { exact: true }), {
      target: { value: "2024-02-29" },
    });
    expect(
      requests.some(
        (r) => r.url.searchParams.get("start_date") === "2024-02-01",
      ),
    ).toBe(false);
    await userEvent.click(
      screen.getByRole("button", { name: "Dönemi uygula" }),
    );
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.url.pathname.endsWith("/summary") &&
            r.url.searchParams.get("start_date") === "2024-02-01" &&
            r.url.searchParams.get("end_date") === "2024-02-29",
        ),
      ).toBe(true),
    );
  });
  it.each([
    [
      "PREVIOUS_NEGATIVE",
      null,
      "Önceki dönem neti negatif; yüzde hesaplanamıyor.",
    ],
    ["BOTH_ZERO", "0.00", "%0,00"],
  ])(
    "renders %s comparison without invented percentages",
    async (state, percentage, label) => {
      handler = (u) =>
        u.pathname.endsWith("/compare")
          ? json({
              currencies: [
                {
                  currency: "TRY",
                  current_net_spending: "0.00",
                  previous_net_spending:
                    state === "BOTH_ZERO" ? "0.00" : "-20.00",
                  absolute_change: state === "BOTH_ZERO" ? "0.00" : "20.00",
                  direction: state === "BOTH_ZERO" ? "UNCHANGED" : "INCREASE",
                  percentage_change: percentage,
                  percentage_state: state,
                },
              ],
            })
          : undefined;
      wrap(<Overview />);
      expect(await screen.findByText(label!)).toBeVisible();
      expect(screen.queryByText(/Infinity|NaN/)).not.toBeInTheDocument();
    },
  );
  it("shows loading while the authoritative summary is pending", () => {
    handler = (u) =>
      u.pathname.endsWith("/summary") ? new Promise(() => {}) : undefined;
    wrap(<Overview />);
    expect(
      screen.getAllByRole("status", { name: "Veriler yükleniyor" }).length,
    ).toBeGreaterThan(0);
  });
  it("renders exact backend metrics with separate currencies, charts, comparison and estimate", async () => {
    wrap(<Overview />);
    const tryGroup = await screen.findByRole("region", {
      name: "TRY harcama özeti",
    });
    expect(within(tryGroup).getByText("1.200,00 TRY")).toBeVisible();
    expect(within(tryGroup).getByText("1.234,56 TRY")).toBeVisible();
    expect(within(tryGroup).getByText("34,56 TRY")).toBeVisible();
    const usdGroup = screen.getByRole("region", { name: "USD harcama özeti" });
    expect(within(usdGroup).getByText("50,01 USD")).toBeVisible();
    expect(within(tryGroup).queryByText(/USD/)).not.toBeInTheDocument();
    expect(
      screen.getByText("Önceki dönem sıfır; yüzde hesaplanamıyor."),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Tahmini ay sonu harcaması" }),
    ).toBeVisible();
    expect(screen.getByText("2.480,00 TRY")).toBeVisible();
    expect(screen.queryByText(/Infinity|NaN/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Kategori dağılımı" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Aylık harcama eğilimi" }),
    ).toBeVisible();
  });
  it("renders empty state instead of invented totals", async () => {
    handler = (u) =>
      u.pathname.endsWith("/summary") ? json({ currencies: [] }) : undefined;
    wrap(<Overview />);
    expect(
      await screen.findByText("Bu dönem için harcama bulunamadı."),
    ).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "TRY harcama özeti" }),
    ).not.toBeInTheDocument();
  });
});
describe("import safety", () => {
  it("renders reconciliation with no skip option for normal candidates", () => {
    render(<PreviewHarness />);
    expect(screen.getByText("✓ Eşleşti")).toBeVisible();
    expect(screen.getByText("SYNTHETIC PURCHASE")).toBeVisible();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "İçe aktarmayı onayla" }),
    ).toBeEnabled();
  });
  it("requires explicit choice for every current duplicate", async () => {
    render(
      <PreviewHarness
        data={{
          ...preview,
          transactions: [
            {
              ...preview.transactions[0],
              duplicate_matches: [{ kind: "heuristic", matched_id: "old" }],
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("button", { name: "İçe aktarmayı onayla" }),
    ).toBeDisabled();
    expect(screen.getByRole("radio", { name: "İçe aktar" })).toBeVisible();
    await userEvent.click(screen.getByRole("radio", { name: "Atla" }));
    expect(
      screen.getByRole("button", { name: "İçe aktarmayı onayla" }),
    ).toBeEnabled();
  });
  it("failed validation has no confirm action", () => {
    render(
      <PreviewHarness
        data={{ ...preview, status: "FAILED", validation_status: "FAILED" }}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "İçe aktarmayı onayla" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeVisible();
  });
  it("pending confirmation is disabled", () => {
    render(<PreviewHarness pending />);
    expect(screen.getByRole("button", { name: "Onaylanıyor…" })).toBeDisabled();
  });
  it("completion renders server counts and clears candidates", () => {
    render(
      <PreviewHarness
        data={{
          ...preview,
          status: "COMPLETED",
          transactions: [],
          counts: {
            ...preview.counts,
            imported_rows: 4,
            skipped_duplicate_rows: 2,
          },
        }}
      />,
    );
    expect(screen.getByText("4 işlem eklendi")).toBeVisible();
    expect(screen.getByText("2 olası tekrar atlandı.")).toBeVisible();
    expect(screen.queryByText("SYNTHETIC PURCHASE")).not.toBeInTheDocument();
  });
  it("uploads selected file and owned account without retaining raw file", async () => {
    wrap(
      <Routes>
        <Route path="/imports" element={<Imports />} />
        <Route path="/imports/:id" element={<ImportDetail />} />
      </Routes>,
      "/imports",
    );
    await screen.findByRole("option", { name: "Sentetik hesap · TRY" });
    await userEvent.selectOptions(
      screen.getByLabelText("Hesap", { exact: true }),
      accountId,
    );
    const file = new File(["%PDF-synthetic"], "synthetic.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText("PDF dosyası seç"), file);
    expect(screen.getByText(/PDF seçildi/)).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Yükle ve önizle" }),
    );
    expect(await screen.findByText("✓ Eşleşti")).toBeVisible();
    const call = requests.find((r) => r.url.pathname.endsWith("/preview"))!;
    expect((call.init.body as FormData).get("account_id")).toBe(accountId);
    expect((call.init.headers as Record<string, string>)["X-Dev-User-ID"]).toBe(
      userId,
    );
    expect(sessionStorage.length).toBe(1);
  });
  it("confirm cannot double submit and refreshes changed duplicate flags", async () => {
    let release: ((r: Response) => void) | undefined;
    let gets = 0;
    handler = (u) => {
      if (u.pathname.endsWith("/confirm"))
        return new Promise((r) => {
          release = r;
        });
      if (u.pathname.endsWith("/imports/batch")) {
        gets++;
        return json(
          gets > 1
            ? {
                ...preview,
                transactions: [
                  {
                    ...preview.transactions[0],
                    duplicate_matches: [
                      { kind: "heuristic", matched_id: "old" },
                    ],
                  },
                ],
              }
            : preview,
        );
      }
      return undefined;
    };
    wrap(
      <Routes>
        <Route path="/imports/:id" element={<ImportDetail />} />
      </Routes>,
      "/imports/batch",
    );
    const button = await screen.findByRole("button", {
      name: "İçe aktarmayı onayla",
    });
    await userEvent.dblClick(button);
    expect(screen.getByRole("button", { name: "Onaylanıyor…" })).toBeDisabled();
    expect(
      requests.filter((r) => r.url.pathname.endsWith("/confirm")),
    ).toHaveLength(1);
    await act(async () =>
      release!(
        json({ detail: { code: "duplicate_resolution_required" } }, 409),
      ),
    );
    expect(await screen.findByRole("radio", { name: "Atla" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "İçe aktarmayı onayla" }),
    ).toBeDisabled();
  });
});
describe("transactions and corrections", () => {
  it("cancelling correction does not send a mutation or report a successful update", async () => {
    wrap(<Transactions />);
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Demo Store sınıflandırmasını düzelt",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByText("İşlem listesi sunucudan güncellendi."),
    ).not.toBeInTheDocument();
    expect(requests.some((r) => r.init.method === "PATCH")).toBe(false);
  });
  it("changing the development user removes cached financial data and sends the new identity", async () => {
    const { client } = wrap(<Transactions />);
    await screen.findByText("SYNTHETIC ORIGINAL");
    client.setQueryData(["analytics", userId, "private-old"], { old: true });
    const nextUser = "33333333-3333-4333-8333-333333333333";
    await userEvent.click(
      screen.getByRole("button", { name: "Bağlamı değiştir" }),
    );
    await userEvent.clear(
      screen.getByLabelText("Geliştirme kullanıcı UUID’si"),
    );
    await userEvent.type(
      screen.getByLabelText("Geliştirme kullanıcı UUID’si"),
      nextUser,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bağlamı kullan", exact: true }),
    );
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.url.pathname.endsWith("/transactions") &&
            new Headers(r.init.headers).get("X-Dev-User-ID") === nextUser,
        ),
      ).toBe(true),
    );
    expect(
      client.getQueryData(["analytics", userId, "private-old"]),
    ).toBeUndefined();
    expect(sessionStorage.getItem("finsight.devUserId")).toBe(nextUser);
  });
  it("renders canonical rows/review status and sends filters and backend offsets", async () => {
    wrap(<Transactions />);
    expect(await screen.findByText("SYNTHETIC ORIGINAL")).toBeVisible();
    expect(screen.getAllByText("İnceleme bekliyor").length).toBeGreaterThan(0);
    await userEvent.type(
      screen.getByLabelText("İşletme veya açıklama"),
      "Demo",
    );
    expect(
      requests.filter((r) => r.url.pathname.endsWith("/transactions")),
    ).toHaveLength(1);
    await userEvent.selectOptions(
      screen.getByLabelText("Kategori", { exact: true }),
      "cafe",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Filtreleri uygula" }),
    );
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.url.searchParams.get("merchant_query") === "Demo" &&
            r.url.searchParams.get("category_id") === "cafe",
        ),
      ).toBe(true),
    );
    await screen.findByText("SYNTHETIC ORIGINAL");
    await userEvent.click(screen.getByRole("button", { name: "Sonraki" }));
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.url.searchParams.get("offset") === "20" &&
            r.url.searchParams.get("limit") === "20",
        ),
      ).toBe(true),
    );
  });
  it("loads categories, preserves raw description and invalidates authoritative analytics on correction", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(["analytics", userId, "summary"], { marker: "old" });
    const close = vi.fn();
    wrap(
      <CorrectionDialog transaction={row} onClose={close} />,
      "/transactions",
      client,
    );
    expect(
      await screen.findByRole("option", { name: "Alışveriş" }),
    ).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC ORIGINAL")).toBeVisible();
    expect(
      screen.queryByRole("textbox", { name: /açıklama/ }),
    ).not.toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("İşletme adı"));
    await userEvent.type(screen.getByLabelText("İşletme adı"), "Demo Coffee");
    await userEvent.selectOptions(
      screen.getByLabelText("Kategori", { exact: true }),
      "shopping",
    );
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(
      screen.getByRole("button", { name: "Değişiklikleri kaydet" }),
    );
    await waitFor(() => expect(close).toHaveBeenCalled());
    const call = requests.find((r) => r.init.method === "PATCH")!;
    expect(JSON.parse(call.init.body as string)).toEqual({
      preferred_merchant_name: "Demo Coffee",
      category_id: "shopping",
      persist_as_rule: true,
    });
    expect(
      client.getQueryState(["analytics", userId, "summary"])?.isInvalidated,
    ).toBe(true);
  });
});
describe("shell", () => {
  it("retains health and opens/closes mobile navigation", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/imports"]}>
          <ProductShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Sunucu bağlı")).toBeVisible();
    const button = screen.getByRole("button", { name: "Menü", exact: true });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("link", { name: /İşlemler/ }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
  it("reports backend offline with retry", async () => {
    handler = (u) =>
      u.pathname.endsWith("/health")
        ? Promise.reject(new Error("offline"))
        : undefined;
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ProductShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Sunucu çevrimdışı")).toBeVisible();
    handler = undefined;
    fireEvent.click(
      screen.getByRole("button", { name: "Bağlantıyı yeniden kontrol et" }),
    );
    expect(await screen.findByText("Sunucu bağlı")).toBeVisible();
  });
});
