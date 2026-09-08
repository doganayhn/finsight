import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { getAnalytics } from "../api/analytics";
import type { AnalyticsResponses } from "../api/analytics";
import type { Params } from "../api/client";
import { useDevelopment } from "../hooks/context";
import {
  Empty,
  ErrorState,
  Loading,
  PageHeading,
  PeriodFields,
} from "../components/ui";
import {
  categoryLabel,
  dateLabel,
  decimal,
  isoDate,
  money,
  monthLabel,
  monthPeriod,
  precedingPeriod,
} from "../utils/presentation";
import type { CategoryBucket, Period } from "../types/contracts";

function useAnalytics<K extends keyof AnalyticsResponses>(
  kind: K,
  userId: string,
  params: Params,
) {
  return useQuery({
    queryKey: ["analytics", userId, kind, params],
    queryFn: ({ signal }) => getAnalytics(kind, userId, params, signal),
  });
}
function CategoryBars({
  rows,
  currency,
}: {
  rows: CategoryBucket[];
  currency: string;
}) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r.net_spending))));
  return (
    <ul className="category-bars">
      {rows.map((row, index) => (
        <li key={row.category_id}>
          <div>
            <span>
              <i style={{ background: `var(--chart-${index % 4})` }} />
              {categoryLabel(row.category_code)}
            </span>
            <strong>{money(row.net_spending, currency)}</strong>
          </div>
          <div className="bar-track" aria-hidden="true">
            <div
              style={{
                width: `${(Math.abs(Number(row.net_spending)) / max) * 100}%`,
                background: row.net_spending.startsWith("-")
                  ? "#b47736"
                  : `var(--chart-${index % 4})`,
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
export function Overview() {
  const { userId, accountId } = useDevelopment();
  const [today] = useState(() => new Date());
  const [period, setPeriod] = useState(() => monthPeriod(today));
  const [draft, setDraft] = useState<Period>(period);
  const [currency, setCurrency] = useState("");
  const [asOf, setAsOf] = useState(() => isoDate(today));
  const [projectionDate, setProjectionDate] = useState(asOf);
  const scope = { account_id: accountId };
  const params = { ...period, ...scope };
  const summary = useAnalytics("summary", userId, params);
  const categories = useAnalytics("categories", userId, params);
  const merchants = useAnalytics("merchants", userId, { ...params, limit: 5 });
  const trend = useAnalytics("trend", userId, params);
  const previous = precedingPeriod(period.start_date, period.end_date);
  const comparison = useAnalytics("compare", userId, {
    ...scope,
    current_start: period.start_date,
    current_end: period.end_date,
    previous_start: previous.start_date,
    previous_end: previous.end_date,
  });
  const projection = useAnalytics("projection", userId, {
    ...scope,
    year: Number(projectionDate.slice(0, 4)),
    month: Number(projectionDate.slice(5, 7)),
    as_of_date: projectionDate,
  });
  const selectedCurrency = summary.data?.currencies.some(
    (r) => r.currency === currency,
  )
    ? currency
    : (summary.data?.currencies[0]?.currency ?? "");
  const categoryRows =
    categories.data?.currencies.find((r) => r.currency === selectedCurrency)
      ?.categories ?? [];
  const months =
    trend.data?.currencies.find((r) => r.currency === selectedCurrency)
      ?.months ?? [];
  const merchantRows =
    merchants.data?.currencies.find((r) => r.currency === selectedCurrency)
      ?.merchants ?? [];
  return (
    <>
      <PageHeading
        title="Genel bakış"
        description="Harcamalarınız, tek bir net görünümde."
      >
        <Link className="button primary" to="/imports">
          ＋ Hesap özeti yükle
        </Link>
      </PageHeading>
      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault();
          setPeriod(draft);
        }}
      >
        <PeriodFields period={draft} onChange={setDraft} today={today} />
        <button type="submit">Dönemi uygula</button>
      </form>
      <p className="scope-note">
        {dateLabel(period.start_date)} — {dateLabel(period.end_date)} · Yalnızca
        içe aktarılan işlemler. Para birimleri ayrı gösterilir.
      </p>
      {summary.isPending ? (
        <Loading />
      ) : summary.isError ? (
        <ErrorState
          error={summary.error}
          retry={() => void summary.refetch()}
        />
      ) : summary.data.currencies.length === 0 ? (
        <Empty>Bu dönem için harcama bulunamadı.</Empty>
      ) : (
        summary.data.currencies.map((row) => (
          <section
            className="currency-summary"
            key={row.currency}
            aria-label={`${row.currency} harcama özeti`}
          >
            <div className="section-caption">
              <span>{row.currency} HARCAMA ÖZETİ</span>
              <span>
                {row.expense_transaction_count} harcama ·{" "}
                {row.refund_transaction_count} iade
              </span>
            </div>
            <div className="metrics">
              <article className="metric net">
                <span>Net harcama</span>
                <strong>{money(row.net_spending, row.currency)}</strong>
                <small>Brüt harcama − iadeler</small>
                <span className="metric-decoration" aria-hidden="true">
                  ↗
                </span>
              </article>
              {(
                [
                  ["gross_spending", "Brüt harcama", "Satın alımlar"],
                  ["refunds", "İadeler", "Harcamadan düşülen"],
                  ["financial_fees", "Finansal ücretler", "Ayrı raporlanır"],
                  ["cash_withdrawals", "Nakit çekimler", "Ayrı raporlanır"],
                ] as const
              ).map(([key, label, note]) => (
                <article className="metric" key={key}>
                  <span>{label}</span>
                  <strong>{money(row[key], row.currency)}</strong>
                  <small>{note}</small>
                </article>
              ))}
            </div>
          </section>
        ))
      )}
      {summary.data && summary.data.currencies.length > 0 && (
        <>
          <div className="section-header">
            <div>
              <h2>Harcamanın ayrıntıları</h2>
              <p>Kategoriler, işletmeler ve zaman içindeki değişim.</p>
            </div>
            <label>
              Grafik para birimi
              <select
                value={selectedCurrency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                {summary.data.currencies.map((r) => (
                  <option key={r.currency}>{r.currency}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="dashboard-grid">
            <section className="panel trend-panel">
              <div className="panel-heading">
                <h3>Aylık harcama eğilimi</h3>
                <span className="badge">{selectedCurrency}</span>
              </div>
              {trend.isPending ? (
                <Loading />
              ) : trend.isError ? (
                <ErrorState
                  error={trend.error}
                  retry={() => void trend.refetch()}
                />
              ) : (
                <>
                  <div
                    className="chart"
                    aria-label={`${selectedCurrency} aylık net harcama grafiği`}
                  >
                    <ResponsiveContainer
                      width="100%"
                      height="100%"
                      minWidth={0}
                    >
                      <LineChart
                        data={months.map((m) => ({
                          label: monthLabel(m.month),
                          value: Number(m.net_spending),
                        }))}
                        margin={{ top: 16, right: 18, left: 0, bottom: 10 }}
                      >
                        <CartesianGrid vertical={false} stroke="#e6eae7" />
                        <XAxis
                          dataKey="label"
                          tickLine={false}
                          axisLine={false}
                          fontSize={12}
                        />
                        <YAxis
                          width={58}
                          tickLine={false}
                          axisLine={false}
                          fontSize={11}
                          tickFormatter={(v) =>
                            new Intl.NumberFormat("tr-TR", {
                              notation: "compact",
                            }).format(Number(v))
                          }
                        />
                        <Line
                          type="linear"
                          dataKey="value"
                          name="Net harcama"
                          stroke="#176b52"
                          strokeWidth={3}
                          dot={{ r: 4 }}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <details className="chart-values">
                    <summary>Grafik değerleri</summary>
                    <ul>
                      {months.map((m) => (
                        <li key={m.month}>
                          {monthLabel(m.month)}
                          <strong>
                            {money(m.net_spending, selectedCurrency)}
                          </strong>
                        </li>
                      ))}
                    </ul>
                  </details>
                </>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h3>Kategori dağılımı</h3>
                <span className="badge">Net · {selectedCurrency}</span>
              </div>
              {categories.isPending ? (
                <Loading />
              ) : categories.isError ? (
                <ErrorState
                  error={categories.error}
                  retry={() => void categories.refetch()}
                />
              ) : categoryRows.length ? (
                <CategoryBars rows={categoryRows} currency={selectedCurrency} />
              ) : (
                <p>Bu para biriminde kategori verisi yok.</p>
              )}
              <p className="footnote">
                Diğer ve inceleme bekleyen harcamalar dahildir. İadeler kendi
                kategorisini azaltır.
              </p>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h3>Öne çıkan işletmeler</h3>
                <span className="badge">İlk 5 · {selectedCurrency}</span>
              </div>
              {merchants.isPending ? (
                <Loading />
              ) : merchants.isError ? (
                <ErrorState
                  error={merchants.error}
                  retry={() => void merchants.refetch()}
                />
              ) : merchantRows.length === 0 ? (
                <p>Bu para biriminde işletme verisi yok.</p>
              ) : (
                <ol className="merchant-list">
                  {merchantRows.map((r, i) => (
                    <li key={`${r.identity_source}-${r.merchant}`}>
                      <span className="rank">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span>
                        {r.merchant ?? "Bilinmeyen işletme"}
                        <small>{r.transaction_count} işlem</small>
                      </span>
                      <strong>{money(r.net_spending, selectedCurrency)}</strong>
                    </li>
                  ))}
                </ol>
              )}
              <p className="footnote">
                Sıralama sunucudan gelir; ilk 5 tüm harcamaları temsil etmez.
              </p>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h3>Dönem karşılaştırması</h3>
                <span aria-hidden="true">↔</span>
              </div>
              <p className="footnote">
                Seçilen dönem ile önceki eşit uzunluktaki dönem:{" "}
                {dateLabel(previous.start_date)} —{" "}
                {dateLabel(previous.end_date)}.
              </p>
              {comparison.isPending ? (
                <Loading />
              ) : comparison.isError ? (
                <ErrorState
                  error={comparison.error}
                  retry={() => void comparison.refetch()}
                />
              ) : (
                comparison.data.currencies.map((r) => (
                  <div className="comparison" key={r.currency}>
                    <span className="badge">{r.currency}</span>
                    <dl>
                      <div>
                        <dt>Seçilen dönem</dt>
                        <dd>{money(r.current_net_spending, r.currency)}</dd>
                      </div>
                      <div>
                        <dt>Önceki dönem</dt>
                        <dd>{money(r.previous_net_spending, r.currency)}</dd>
                      </div>
                      <div>
                        <dt>
                          {r.direction === "INCREASE"
                            ? "Artış"
                            : r.direction === "DECREASE"
                              ? "Azalış"
                              : "Değişim yok"}
                        </dt>
                        <dd>{money(r.absolute_change, r.currency)}</dd>
                      </div>
                    </dl>
                    <p className="comparison-note">
                      {r.percentage_change !== null
                        ? `%${decimal(r.percentage_change)}`
                        : r.percentage_state === "PREVIOUS_NEGATIVE"
                          ? "Önceki dönem neti negatif; yüzde hesaplanamıyor."
                          : "Önceki dönem sıfır; yüzde hesaplanamıyor."}
                    </p>
                  </div>
                ))
              )}
            </section>
          </div>
        </>
      )}
      <section className="panel projection">
        <div>
          <p className="eyebrow">HARCAMA HIZINIZ</p>
          <h2>Tahmini ay sonu harcaması</h2>
          <p>Bu harcama hızı devam ederse…</p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setProjectionDate(asOf);
          }}
        >
          <label>
            Hesaplamanın son günü
            <input
              type="date"
              required
              min="1900-01-01"
              max="2100-12-31"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <button>Tahmini güncelle</button>
        </form>
        {projection.isPending ? (
          <Loading />
        ) : projection.isError ? (
          <ErrorState
            error={projection.error}
            retry={() => void projection.refetch()}
          />
        ) : (
          <div className="projection-results">
            {projection.data.currencies.map((r) => (
              <div key={r.currency}>
                <strong>{money(r.projected_month_spending, r.currency)}</strong>
                <p>
                  {projection.data.elapsed_days} /{" "}
                  {projection.data.days_in_month} gün · Gözlenen net:{" "}
                  {money(r.observed_net_spending, r.currency)}
                </p>
                <p>
                  Günlük ortalama: {money(r.average_daily_spending, r.currency)}
                </p>
              </div>
            ))}
            {projection.data.currencies.length === 0 && (
              <p>Bu ay için henüz işlem yok.</p>
            )}
          </div>
        )}
        <p className="footnote full">
          Tahmin, ayın ilk gününden seçilen güne kadar gözlenen harcamanın sabit
          günlük hızla süreceğini varsayar. Kaynak kapsamı eksik olabilir.
          Negatif net harcamada tahmin sıfırdır. Bakiye veya kalan para tahmini
          değildir.
        </p>
      </section>
    </>
  );
}
